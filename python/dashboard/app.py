"""Painel web (FastAPI): roda um episódio SUMO + Unity + visão e transmite o que acontece.

O episódio roda numa thread própria, pelo mesmo ``Environment.run`` das
avaliações (mesma camada de segurança, mesma visão e mesmas versões de
``experiments.version_policies``). A API só escolhe o cenário, a versão e a
fonte da preempção, despacha viaturas e lê a telemetria; nada do painel entra
na decisão da política.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import queue
import threading
import traceback
from typing import Any

import cv2
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yaml

from bridge import UnityBridge
from controller.preemption import PreemptionSettings
from dashboard.telemetry import APPROACHES, build_telemetry
from experiments.episode_runner import EpisodeSettings
from experiments.sumo_environment import EMERGENCY_DETECTIONS, Environment
from experiments.version_policies import build_version_policies
from experiments.visual_observer import build_unity_observer
from sumo.emergency import EmergencySettings
from vision.visual_debug import VisualDebugger


SCENARIOS = ("calibrated", "calibrated_ped", "original")
# Controladores oferecidos no painel (nomes do código). O produto exibido é o
# TraffIQ v4, que decide com o DQN estado v2; o DQN estado v3 é experimento e
# não aparece aqui.
VERSIONS = ("v2", "baseline", "v1", "max_pressure")
PREEMPTION_SOURCES = ("none", *EMERGENCY_DETECTIONS)
# Espera média por veículo do ciclo fixo em cada cenário, na avaliação oficial
# (compare_versions, seeds 201–203, 300 s + 1800 s; README e
# results/evaluation/versoes-<cenário>-*.json). O ciclo fixo não depende da
# percepção. É a referência da "redução" do painel, que mede ao vivo a mesma
# métrica (ExperimentMetricsCollector.progress).
FIXED_TIME_REFERENCE_S = {"calibrated": 13.0, "calibrated_ped": 20.8, "original": 14.9}
# Amostra mínima (s simulados depois do aquecimento) antes de mostrar a redução.
MIN_SAMPLE_S = 600.0
# Com o detector genérico (COCO) a câmera não reconhece viaturas.
VISUAL_PREEMPTION = ("vision", "both")
VERSION_LABELS = {"v2": "TraffIQ (IA, v4)", "baseline": "Tempo fixo (convencional)", "v1": "Regra de fila (v1)",
                  "max_pressure": "Max-pressure (referência acadêmica)"}


class StartRequest(BaseModel):
    scenario: str = "calibrated"
    version: str = "v2"
    preemption: str = "v2i"
    seed: int = 201


class EmergencyRequestBody(BaseModel):
    approach: str
    exit: str | None = None  # None: sorteia entre as saídas da aproximação


# Saídas da rede SP (Cruzamento.net.xml): E0 vai ao Norte, E1 ao Leste, E5 ao Oeste.
EXIT_EDGES = {"north": "E0", "east": "E1", "west": "E5"}


@dataclass(frozen=True, slots=True)
class PanelSettings:
    base_dir: Path
    vision_args: Any
    warmup_s: float = 30.0
    control_s: float = 36000.0
    # True quando o api_server caiu no detector genérico (COCO, sem a classe de viatura).
    generic_detector: bool = False


class EpisodeRunner:
    """Thread do episódio: espera um pedido de início e roda até parar ou acabar."""

    def __init__(self, settings: PanelSettings) -> None:
        self.settings = settings
        self.config: dict[str, Any] = yaml.safe_load((settings.base_dir / "configs" / "sp.yaml").read_text(encoding="utf-8"))
        models = settings.base_dir.parent / "results" / "models"
        # Mesmos checkpoints padrão de compare_versions/evaluate_preemption. A v1
        # é a heurística (sem checkpoint); o da v1.1 só é lido se ela for pedida,
        # e o painel não a oferece.
        self.v1_1_checkpoint = models / "visual-dqn-sp-best.pt"
        self.checkpoints = {"v2": models / "dqn-v2-sem-motos-best.pt"}
        self.announce_before_s = EmergencySettings.from_config(self.config).announce_before_s
        self.state: dict[str, Any] = {"is_running": False, "status": "parado", "request": None, "telemetry": None,
                                      "dispatched": [], "error": None, "last_summary": None}
        self.frames: dict[str, bytes | None] = {camera: None for camera in APPROACHES}
        self._pending: queue.Queue[StartRequest] = queue.Queue(maxsize=1)
        self._dispatch: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._stop_episode = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None
        self._debugger: VisualDebugger | None = None
        # Um só observador para o processo: o step_id dele cresce entre episódios,
        # e frames atrasados de um episódio nunca casam com um step do seguinte.
        self._observer: Any = None
        self._bridge_ready = threading.Event()

    # ---- controle (chamado pela API) ----
    def start(self, request: StartRequest) -> None:
        if request.scenario not in SCENARIOS or request.version not in VERSIONS or request.preemption not in PREEMPTION_SOURCES:
            raise ValueError("Cenário, versão ou fonte de preempção desconhecidos.")
        if self.settings.generic_detector and request.preemption in VISUAL_PREEMPTION:
            raise ValueError("O detector genérico não reconhece ambulâncias: use a prioridade só pelo V2I (GPS) ou desligada.")
        checkpoint = self.checkpoints.get(request.version)
        if checkpoint is not None and not checkpoint.exists():
            raise ValueError(f"Checkpoint não encontrado: {checkpoint}")
        if self._thread is None or not self._thread.is_alive() or not self._bridge_ready.is_set():
            raise ValueError(self.state["error"] or "A conexão com a Unity (porta de frames) não está pronta.")
        if self.state["is_running"] or not self._pending.empty():
            raise ValueError("Já há uma demonstração em execução; encerre-a antes de iniciar outra.")
        self._clear_dispatches()
        self.frames = {camera: None for camera in APPROACHES}
        self._stop_episode.clear()
        self._pending.put(request)
        self.state = {**self.state, "is_running": True, "status": "iniciando", "request": request.model_dump(),
                      "telemetry": None, "dispatched": [], "error": None}

    def stop(self) -> None:
        self._stop_episode.set()

    def _clear_dispatches(self) -> None:
        while not self._dispatch.empty():
            self._dispatch.get_nowait()

    def emergency_routes(self) -> dict[str, list[str]]:
        """Saídas possíveis por aproximação, pelas rotas de ``emergency.routes`` do sp.yaml."""
        names = {edge: name for name, edge in EXIT_EDGES.items()}
        routes = EmergencySettings.from_config(self.config).routes
        return {approach: [names[to_edge] for _, to_edge in routes[approach]] for approach in APPROACHES}

    def dispatch_emergency(self, approach: str, exit_name: str | None = None) -> None:
        if approach not in APPROACHES:
            raise ValueError(f"Aproximação desconhecida: {approach}.")
        if exit_name is not None and exit_name not in self.emergency_routes()[approach]:
            raise ValueError(f"Sem rota de {approach} para {exit_name}.")
        if not self.state["is_running"]:
            raise ValueError("Inicie a demonstração antes de acionar uma ambulância.")
        self._dispatch.put((approach, exit_name))

    def launch(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="episodio-painel", daemon=True)
        self._thread.start()

    def shutdown(self, timeout_s: float = 15.0) -> None:
        """Para o episódio e espera a thread fechar o TraCI e os sockets."""
        self._shutdown.set()
        self._stop_episode.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)

    # ---- thread do episódio ----
    def _loop(self) -> None:
        # O VisualDebugger cria o diretório, mas o painel só usa o annotate (nada é gravado).
        self._debugger = VisualDebugger(str(self.settings.base_dir.parent / "results" / "vision" / "painel"))
        try:
            bridge = UnityBridge.from_config(self.config)
            bridge.start_frame_server()
        except Exception as error:  # noqa: BLE001 - ex.: porta de frames já em uso por outro script
            traceback.print_exc()
            self.state = {**self.state, "error": f"Falha ao abrir a conexão com a Unity: {error}"}
            return
        self._bridge_ready.set()
        try:
            while not self._shutdown.is_set():
                try:
                    request = self._pending.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    self._run_episode(request, bridge)
                except Exception as error:  # noqa: BLE001 - o painel mostra o erro e continua vivo
                    traceback.print_exc()
                    self.state = {**self.state, "error": str(error)}
                finally:
                    self._clear_dispatches()
                    self.state = {**self.state, "is_running": False, "status": "parado"}
        finally:
            bridge.close()

    def _run_episode(self, request: StartRequest, bridge: UnityBridge) -> None:
        version = build_version_policies(self.config, [request.version], self.v1_1_checkpoint, self.checkpoints["v2"])[0]
        environment = Environment(self.config, self.settings.base_dir, request.scenario,
                                  EpisodeSettings(self.settings.warmup_s, self.settings.control_s, version.decision_interval_s),
                                  state_version=version.state_version)
        if self._observer is None:
            # Geometrias, semáforo e aquecimento vêm do sp.yaml e do painel: iguais em todos os cenários.
            self._observer = build_unity_observer(self.config, self.settings.base_dir, self.settings.vision_args, environment, bridge)
        observer = self._observer
        preemption = None if request.preemption == "none" else PreemptionSettings.from_config(self.config)
        last_results: list[Any] = [None]

        def on_step(info: dict[str, Any]) -> None:
            if self._stop_episode.is_set():
                raise InterruptedError("Episódio interrompido pelo painel.")
            traffic = environment.emergency_traffic
            while traffic is not None and not self._dispatch.empty():
                approach, exit_name = self._dispatch.get_nowait()
                to_edge = None if exit_name is None else EXIT_EDGES[exit_name]
                vehicle_id = traffic.dispatch(approach, float(info["sim_time"]), to_edge=to_edge)
                self.state = {**self.state, "dispatched": [*self.state["dispatched"], {
                    "id": vehicle_id, "approach": approach, "exit": exit_name, "sim_time": info["sim_time"]}]}
            self.state = {**self.state, "status": "rodando", "telemetry": build_telemetry(info)}
            results = getattr(observer, "last_results", None)
            if results is not None and results is not last_results[0]:
                last_results[0] = results
                self._publish_frames(results)

        print(f"painel_episodio_inicio scenario={request.scenario} version={request.version} "
              f"preemption={request.preemption} seed={request.seed}")
        try:
            outcome, _ = environment.run(request.seed, version.policy, observer=observer, on_step=on_step,
                                         emergency=EmergencySettings.from_config(self.config), preemption=preemption,
                                         emergency_detection="v2i" if preemption is None else request.preemption)
        except InterruptedError:
            print("painel_episodio_interrompido")
            return
        metrics = outcome.metrics
        self.state = {**self.state, "last_summary": {
            "mean_waiting_time_seconds": metrics.get("mean_waiting_time_seconds"),
            "arrived_vehicles": metrics.get("arrived_vehicles"),
            "pedestrian_mean_waiting_s": metrics.get("pedestrian_mean_waiting_s"),
            "emergency_mean_total_loss_s": metrics.get("emergency", {}).get("mean_total_loss_at_crossing_s"),
        }}

    def _publish_frames(self, results: dict[str, Any]) -> None:
        for camera_id, result in results.items():
            try:
                annotated = self._debugger.annotate(result.frame, result.detections, result.tracks, result.raw_counts,
                                                    result.rois, result.queue_counts)
                ok, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    self.frames[camera_id] = buffer.tobytes()
            except Exception as error:  # noqa: BLE001 - um frame ruim não derruba o episódio
                print(f"painel_frame_erro camera={camera_id} erro={error}")


def create_app(settings: PanelSettings) -> FastAPI:
    runner = EpisodeRunner(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        runner.launch()
        yield
        runner.shutdown()

    app = FastAPI(title="TraffIQ — painel", lifespan=lifespan)
    app.state.runner = runner
    app.mount("/dashboard", StaticFiles(directory=settings.base_dir / "static", html=True), name="static")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse("/dashboard/")

    @app.get("/api/options")
    async def options() -> dict[str, Any]:
        return {"scenarios": list(SCENARIOS), "versions": [{"id": key, "label": VERSION_LABELS[key]} for key in VERSIONS],
                "preemption": list(PREEMPTION_SOURCES), "approaches": list(APPROACHES),
                "emergency_routes": runner.emergency_routes(), "announce_before_s": runner.announce_before_s,
                "fixed_time_reference_s": FIXED_TIME_REFERENCE_S, "min_sample_s": MIN_SAMPLE_S,
                "generic_detector": settings.generic_detector}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return runner.state

    @app.post("/api/start")
    async def start(request: StartRequest) -> dict[str, Any]:
        try:
            runner.start(request)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "ok"}

    @app.post("/api/stop")
    async def stop() -> dict[str, Any]:
        runner.stop()
        return {"status": "ok"}

    @app.post("/api/emergency")
    async def emergency(body: EmergencyRequestBody) -> dict[str, Any]:
        try:
            runner.dispatch_emergency(body.approach, body.exit)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "ok"}

    @app.websocket("/ws/telemetry")
    async def telemetry(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(runner.state)
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            return

    async def frames(camera_id: str):
        sent = None
        while True:
            frame = runner.frames.get(camera_id)
            # Os frames mudam ~1 vez por step: só reenvia quando há um novo.
            if frame and frame is not sent:
                sent = frame
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            await asyncio.sleep(0.1)

    @app.get("/api/video/{camera_id}")
    async def video(camera_id: str) -> StreamingResponse:
        if camera_id not in APPROACHES:
            raise HTTPException(status_code=404, detail="Câmera desconhecida.")
        return StreamingResponse(frames(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

    return app
