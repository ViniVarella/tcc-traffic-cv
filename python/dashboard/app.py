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
from dataclasses import dataclass, replace
import json
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
# Espera média por veículo do ciclo fixo em cada cenário, na avaliação oficial: a
# referência da "redução" do painel, que mede ao vivo a mesma métrica
# (ExperimentMetricsCollector.progress). Lida de results/evaluation; estes valores
# (README, 2026-10-14) só valem se o arquivo faltar ou for de outro protocolo.
FIXED_TIME_REFERENCE_S = {"calibrated": 13.0, "calibrated_ped": 20.8, "original": 14.9}
# O mesmo para a espera só de quem parou (mean_waiting_time_stopped_seconds; 2026-10-20).
FIXED_TIME_STOPPED_REFERENCE_S = {"calibrated": 23.1, "calibrated_ped": 34.3, "original": 22.7}
OFFICIAL_PROTOCOL = {"warmup_s": 300.0, "control_s": 1800.0, "seeds": [201, 202, 203]}


def load_fixed_time_reference(results_dir: Path, metric: str = "mean_waiting_time_seconds",
                              fallback: dict[str, float] = FIXED_TIME_REFERENCE_S) -> tuple[dict[str, float], dict[str, str]]:
    """Referência do tempo fixo por cenário e a origem de cada uma ("avaliação" ou "valor embutido").

    Lê ``metric`` em ``versoes-<cenário>-oracle.json`` (o ciclo fixo não depende da
    percepção) e só o aceita no protocolo oficial (seeds 201–203, 300 s + 1800 s).
    """
    values, sources = dict(fallback), {scenario: "valor embutido" for scenario in fallback}
    for scenario in fallback:
        try:
            report = json.loads((results_dir / f"versoes-{scenario}-oracle.json").read_text(encoding="utf-8"))
            if any(report.get(key) != value for key, value in OFFICIAL_PROTOCOL.items()):
                continue
            values[scenario] = round(float(report["versions"]["baseline"]["mean"][metric]), 1)
            sources[scenario] = "avaliação"
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return values, sources
# Amostra mínima (s simulados depois do aquecimento) antes de mostrar a redução.
# Com 5 min a média do tempo fixo fica a ~10% da de 30 min (seeds 201–203).
MIN_SAMPLE_S = 300.0
# Com o detector genérico (COCO) a câmera não reconhece viaturas.
VISUAL_PREEMPTION = ("vision", "both")
VERSION_LABELS = {"v2": "TraffIQ (IA, v4)", "baseline": "Tempo fixo (convencional)", "v1": "Regra de fila (v1)",
                  "max_pressure": "Max-pressure (referência acadêmica)"}


class StartRequest(BaseModel):
    scenario: str = "calibrated"
    version: str = "v2"
    preemption: str = "v2i"
    seed: int = 201
    # Agenda automática de viaturas (uma a cada ~5 min, como nas avaliações de
    # preempção). Desligada, só entram as do botão.
    auto_emergencies: bool = False


class EmergencyRequestBody(BaseModel):
    approach: str
    exit: str | None = None  # None: sorteia entre as saídas da aproximação


# Saídas da rede SP (Cruzamento.net.xml): E0 vai ao Norte, E1 ao Leste, E5 ao Oeste.
EXIT_EDGES = {"north": "E0", "east": "E1", "west": "E5"}
EXIT_NAMES = {edge: name for name, edge in EXIT_EDGES.items()}


def emergency_board(traffic: Any, preemption: Any, sim_time: float) -> dict[str, Any]:
    """Viaturas a caminho (lista do painel) e as contagens, com a que a preempção atende agora."""
    active = getattr(preemption, "active", None)
    serving = None if active is None else active.vehicle_id
    vehicles = [{**item, "exit": EXIT_NAMES.get(item["to_edge"]), "served": item["id"] == serving}
                for item in traffic.live_status(sim_time)]
    return {"vehicles": vehicles, "counts": traffic.announced_counts(sim_time)}


@dataclass(frozen=True, slots=True)
class PanelSettings:
    base_dir: Path
    vision_args: Any
    warmup_s: float = 300.0
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
        self.checkpoints = {"v2": models / "dqn-v2-traffiq-best.pt"}
        self.announce_before_s = EmergencySettings.from_config(self.config).announce_before_s
        evaluation_dir = settings.base_dir.parent / "results" / "evaluation"
        self.fixed_time_reference, self.fixed_time_reference_source = load_fixed_time_reference(evaluation_dir)
        self.fixed_time_stopped_reference, _ = load_fixed_time_reference(
            evaluation_dir, "mean_waiting_time_stopped_seconds", FIXED_TIME_STOPPED_REFERENCE_S)
        self.state: dict[str, Any] = {"is_running": False, "paused": False, "status": "parado", "request": None, "telemetry": None,
                                      "error": None, "last_summary": None}
        # As rotas da API (event loop) e o on_step (thread do episódio) reescrevem o
        # estado: a trava evita que uma escrita apague a outra (ex.: a pausa).
        self._state_lock = threading.Lock()
        self.frames: dict[str, bytes | None] = {camera: None for camera in APPROACHES}
        self._pending: queue.Queue[StartRequest] = queue.Queue(maxsize=1)
        self._dispatch: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self._stop_episode = threading.Event()
        # Liberado = rodando; limpo = pausado (o laço espera no on_step, antes do próximo step).
        self._resume = threading.Event()
        self._resume.set()
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
        self._resume.set()
        self._pending.put(request)
        self._update_state(is_running=True, paused=False, status="iniciando", request=request.model_dump(), telemetry=None,
                           error=None)

    def stop(self) -> None:
        self._stop_episode.set()
        self._resume.set()  # um episódio pausado precisa voltar ao laço para encerrar

    def pause(self) -> None:
        """Congela a simulação: o SUMO só avança quando o Python pede o próximo step."""
        if not self.state["is_running"]:
            raise ValueError("Não há demonstração em execução para pausar.")
        with self._state_lock:
            self._resume.clear()
            self.state = {**self.state, "paused": True, "status": "pausado"}

    def resume(self) -> None:
        if not self.state["is_running"]:
            raise ValueError("Não há demonstração em execução para retomar.")
        with self._state_lock:
            self.state = {**self.state, "paused": False, "status": "rodando"}
            self._resume.set()

    def _update_state(self, **changes: Any) -> None:
        with self._state_lock:
            self.state = {**self.state, **changes}

    def _wait_while_paused(self) -> None:
        while not self._resume.wait(timeout=0.2):
            if self._stop_episode.is_set():
                break

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

    def begin_shutdown(self) -> None:
        """Sinal de encerramento do servidor: para o episódio e solta câmeras e telemetria."""
        self._shutdown.set()
        self._stop_episode.set()
        self._resume.set()

    @property
    def closing(self) -> bool:
        return self._shutdown.is_set()

    def shutdown(self, timeout_s: float = 15.0) -> None:
        """Para o episódio e espera a thread fechar o TraCI e os sockets."""
        self.begin_shutdown()
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
            self._update_state(error=f"Falha ao abrir a conexão com a Unity: {error}")
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
                    self._update_state(error=str(error))
                finally:
                    self._clear_dispatches()
                    self._update_state(is_running=False, paused=False, status="parado")
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
            self._wait_while_paused()
            if self._stop_episode.is_set():
                raise InterruptedError("Episódio interrompido pelo painel.")
            traffic = environment.emergency_traffic
            while traffic is not None and not self._dispatch.empty():
                approach, exit_name = self._dispatch.get_nowait()
                to_edge = None if exit_name is None else EXIT_EDGES[exit_name]
                traffic.dispatch(approach, float(info["sim_time"]), to_edge=to_edge)
            telemetry = build_telemetry(info)
            if traffic is not None:
                telemetry["emergencies"] = emergency_board(traffic, environment.emergency_preemption, float(info["sim_time"]))
            with self._state_lock:
                self.state = {**self.state, "status": "pausado" if self.state["paused"] else "rodando",
                              "telemetry": telemetry}
            results = getattr(observer, "last_results", None)
            if results is not None and results is not last_results[0]:
                last_results[0] = results
                self._publish_frames(results)

        print(f"painel_episodio_inicio scenario={request.scenario} version={request.version} "
              f"preemption={request.preemption} seed={request.seed} auto_emergencies={request.auto_emergencies}")
        try:
            outcome, _ = environment.run(request.seed, version.policy, observer=observer, on_step=on_step,
                                         emergency=replace(EmergencySettings.from_config(self.config),
                                                           scheduled=request.auto_emergencies), preemption=preemption,
                                         emergency_detection="v2i" if preemption is None else request.preemption)
        except InterruptedError:
            print("painel_episodio_interrompido")
            return
        metrics = outcome.metrics
        self._update_state(last_summary={
            "mean_waiting_time_seconds": metrics.get("mean_waiting_time_seconds"),
            "arrived_vehicles": metrics.get("arrived_vehicles"),
            "pedestrian_mean_waiting_s": metrics.get("pedestrian_mean_waiting_s"),
            "emergency_mean_total_loss_s": metrics.get("emergency", {}).get("mean_total_loss_at_crossing_s"),
        })

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
                "fixed_time_reference_s": runner.fixed_time_reference,
                "fixed_time_reference_source": runner.fixed_time_reference_source,
                "fixed_time_stopped_reference_s": runner.fixed_time_stopped_reference, "min_sample_s": MIN_SAMPLE_S, "warmup_s": settings.warmup_s,
                "reference_warmup_s": OFFICIAL_PROTOCOL["warmup_s"],
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

    @app.post("/api/pause")
    async def pause() -> dict[str, Any]:
        try:
            runner.pause()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "ok"}

    @app.post("/api/resume")
    async def resume() -> dict[str, Any]:
        try:
            runner.resume()
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
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
            while not runner.closing:
                await websocket.send_json(runner.state)
                await asyncio.sleep(0.5)
            await websocket.close()
        except WebSocketDisconnect:
            return

    async def frames(camera_id: str):
        sent = None
        # Termina no encerramento do servidor, para ele não esperar o stream para sempre.
        while not runner.closing:
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

    app.state.runner = runner
    return app
