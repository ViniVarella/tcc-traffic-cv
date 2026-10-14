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
VERSIONS = ("baseline", "v1", "v2", "v3", "max_pressure")
PREEMPTION_SOURCES = ("none", *EMERGENCY_DETECTIONS)
VERSION_LABELS = {"baseline": "Ciclo fixo 40/40", "v1": "v1 — heurística por fila", "v2": "v2 — DQN (41 entradas)",
                  "v3": "v3 — DQN com pedestres (44 entradas)", "max_pressure": "Max-pressure (referência)"}


class StartRequest(BaseModel):
    scenario: str = "calibrated"
    version: str = "v2"
    preemption: str = "v2i"
    seed: int = 201


class EmergencyRequestBody(BaseModel):
    approach: str


@dataclass(frozen=True, slots=True)
class PanelSettings:
    base_dir: Path
    vision_args: Any
    warmup_s: float = 30.0
    control_s: float = 36000.0


class EpisodeRunner:
    """Thread do episódio: espera um pedido de início e roda até parar ou acabar."""

    def __init__(self, settings: PanelSettings) -> None:
        self.settings = settings
        self.config: dict[str, Any] = yaml.safe_load((settings.base_dir / "configs" / "sp.yaml").read_text(encoding="utf-8"))
        models = settings.base_dir.parent / "results" / "models"
        # Mesmos checkpoints padrão de compare_versions/evaluate_preemption.
        self.checkpoints = {"v1": models / "visual-dqn-sp-best.pt", "v2": models / "dqn-v2-sem-motos-best.pt",
                            "v3": models / "dqn-v3-fase-curta-best.pt"}
        self.state: dict[str, Any] = {"is_running": False, "status": "parado", "request": None, "telemetry": None,
                                      "dispatched": [], "error": None, "last_summary": None}
        self.frames: dict[str, bytes | None] = {camera: None for camera in APPROACHES}
        self._pending: queue.Queue[StartRequest] = queue.Queue(maxsize=1)
        self._dispatch: queue.Queue[str] = queue.Queue()
        self._stop_episode = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None
        self._debugger: VisualDebugger | None = None

    # ---- controle (chamado pela API) ----
    def start(self, request: StartRequest) -> None:
        if request.scenario not in SCENARIOS or request.version not in VERSIONS or request.preemption not in PREEMPTION_SOURCES:
            raise ValueError("Cenário, versão ou fonte de preempção desconhecidos.")
        if request.version == "v3" and request.scenario != "calibrated_ped":
            raise ValueError("A v3 só roda no cenário com pedestres (calibrated_ped).")
        checkpoint = self.checkpoints.get(request.version)
        if checkpoint is not None and not checkpoint.exists():
            raise ValueError(f"Checkpoint não encontrado: {checkpoint}")
        if self.state["is_running"] or not self._pending.empty():
            raise ValueError("Já há um episódio rodando; pare antes de iniciar outro.")
        self._stop_episode.clear()
        self._pending.put(request)
        self.state = {**self.state, "is_running": True, "status": "iniciando", "request": request.model_dump(),
                      "telemetry": None, "dispatched": [], "error": None}

    def stop(self) -> None:
        self._stop_episode.set()

    def dispatch_emergency(self, approach: str) -> None:
        if approach not in APPROACHES:
            raise ValueError(f"Aproximação desconhecida: {approach}.")
        if not self.state["is_running"]:
            raise ValueError("Inicie um episódio antes de despachar uma viatura.")
        self._dispatch.put(approach)

    def launch(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="episodio-painel", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._shutdown.set()
        self._stop_episode.set()

    # ---- thread do episódio ----
    def _loop(self) -> None:
        # Só anota os frames (não grava nada nesse diretório).
        self._debugger = VisualDebugger(str(self.settings.base_dir.parent / "results" / "vision" / "painel"))
        bridge = UnityBridge.from_config(self.config)
        try:
            bridge.start_frame_server()
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
                    self.state = {**self.state, "is_running": False, "status": "parado"}
        finally:
            bridge.close()

    def _run_episode(self, request: StartRequest, bridge: UnityBridge) -> None:
        version = build_version_policies(self.config, [request.version], self.checkpoints["v1"], self.checkpoints["v2"],
                                         self.checkpoints["v3"])[0]
        environment = Environment(self.config, self.settings.base_dir, request.scenario,
                                  EpisodeSettings(self.settings.warmup_s, self.settings.control_s, version.decision_interval_s),
                                  state_version=version.state_version)
        observer = build_unity_observer(self.config, self.settings.base_dir, self.settings.vision_args, environment, bridge)
        preemption = None if request.preemption == "none" else PreemptionSettings.from_config(self.config)
        last_results: list[Any] = [None]

        def on_step(info: dict[str, Any]) -> None:
            if self._stop_episode.is_set():
                raise InterruptedError("Episódio interrompido pelo painel.")
            traffic = getattr(environment, "emergency_traffic", None)
            while traffic is not None and not self._dispatch.empty():
                approach = self._dispatch.get_nowait()
                vehicle_id = traffic.dispatch(approach, float(info["sim_time"]))
                self.state = {**self.state, "dispatched": [*self.state["dispatched"],
                                                           {"id": vehicle_id, "approach": approach, "sim_time": info["sim_time"]}]}
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

    app = FastAPI(title="Traffic CV — painel", lifespan=lifespan)
    app.state.runner = runner
    app.mount("/dashboard", StaticFiles(directory=settings.base_dir / "static", html=True), name="static")

    @app.get("/")
    async def root() -> RedirectResponse:
        return RedirectResponse("/dashboard/")

    @app.get("/api/options")
    async def options() -> dict[str, Any]:
        return {"scenarios": list(SCENARIOS), "versions": [{"id": key, "label": VERSION_LABELS[key]} for key in VERSIONS],
                "preemption": list(PREEMPTION_SOURCES), "approaches": list(APPROACHES)}

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
            runner.dispatch_emergency(body.approach)
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
        while True:
            frame = runner.frames.get(camera_id)
            if frame:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            await asyncio.sleep(0.1)

    @app.get("/api/video/{camera_id}")
    async def video(camera_id: str) -> StreamingResponse:
        if camera_id not in APPROACHES:
            raise HTTPException(status_code=404, detail="Câmera desconhecida.")
        return StreamingResponse(frames(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

    return app
