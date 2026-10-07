import asyncio
import json
import threading
import time
import os
import io
from pathlib import Path
from typing import Any

import yaml
import cv2
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from bridge import UnityBridge
from controller import DqnAgent
from controller.policies import FixedCyclePolicy, MaxPressurePolicy
from experiments.episode_runner import DqnPolicy, EpisodeSettings
from experiments.sumo_environment import Environment
from experiments.visual_observer import build_unity_observer
from vision.visual_debug import VisualDebugger

app = FastAPI(title="Traffic CV - Centro de Comando")

static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="static")

# Estado global sincronizado com o frontend
simulation_state = {
    "is_running": False,
    "current_policy": "dqn",
    "south_queue": 0,
    "east_queue": 0,
    "west_queue": 0,
    "avg_waiting_time": 0.0,
    "sim_time": 0.0
}

active_connections = []
latest_frames = {"south": None, "east": None, "west": None}
debugger = VisualDebugger("") # Instância dummy para não salvar arquivos em disco

should_stop = False
inject_emergency_flag = False
simulation_thread = None

class MockArgs:
    def __init__(self, base_dir: Path):
        self.scenario = "calibrated"
        self.camera_ids = "south,east,west"
        
        custom_yolo = base_dir.parent / "runs" / "results" / "models" / "yolov8n-unity-cam60-2cls-960" / "weights" / "best.pt"
        if custom_yolo.exists():
            self.model = str(custom_yolo)
            self.classes = "0,1"
        else:
            print("Aviso: Modelo YOLO customizado não encontrado. Baixando yolov8n.pt padrão (COCO).")
            self.model = "yolov8n.pt"
            self.classes = "2,3,5,7" # COCO: car, motorcycle, bus, truck
            
        self.confidence = 0.15
        self.image_size = 960
        self.frame_rate = 1.0
        self.track_match_threshold = 0.6
        self.send_interval = 0.05  # Mais rápido para a feira
        self.prime_seconds = 5.0
        self.ground_offset = None
        self.no_oracle_shadow = True

def run_simulation_loop():
    """Loop principal: aguarda o botão 'Iniciar' e roda episódios via Environment.run()."""
    global simulation_state, latest_frames, should_stop, inject_emergency_flag

    base_dir = Path(__file__).resolve().parents[1]
    config_path = base_dir / "configs" / "sp.yaml"
    config = yaml.safe_load(config_path.resolve().read_text(encoding="utf-8"))

    args = MockArgs(base_dir)
    settings = EpisodeSettings(warmup_s=30.0, control_s=36000.0, decision_interval_s=5.0)  # 10 horas
    environment = Environment(config, base_dir, args.scenario, settings)
    bridge = UnityBridge.from_config(config)

    try:
        bridge.start_frame_server()
        observer = build_unity_observer(config, base_dir, args, environment, bridge)

        while not should_stop:
            # Aguarda até que o usuário clique em "Iniciar"
            if not simulation_state["is_running"]:
                time.sleep(0.5)
                continue

            print("Iniciando episódio do SUMO...")
            # Decide política — procura o melhor modelo DQN disponível
            models_dir = base_dir.parent / "results" / "models"
            dqn_candidates = [
                models_dir / "dqn-v2-pretrain-best.pt",                    # pré-treino padrão
                models_dir / "dqn-v2-roi60-mix-pretrain-best.pt",          # variante com ROI 60
                models_dir / "dqn-v2-finetune-best.pt",                    # ajuste fino visual
            ]
            dqn_model = next((p for p in dqn_candidates if p.exists()), None)

            if simulation_state["current_policy"] == "dqn" and dqn_model is None:
                print("Aviso: Modelo DQN não encontrado. Fazendo fallback para Ciclo Fixo.")
                print(f"  Procurados: {[str(p) for p in dqn_candidates]}")
                simulation_state["current_policy"] = "fixed"

            if simulation_state["current_policy"] == "fixed":
                policy = FixedCyclePolicy()
            else:
                agent = DqnAgent.load(dqn_model, device="cpu")
                policy = DqnPolicy(agent)

            # Callback on_step: atualiza telemetria e frames para o dashboard
            def on_step(info: dict[str, Any]) -> None:
                global simulation_state, latest_frames, should_stop
                if should_stop or not simulation_state["is_running"]:
                    raise InterruptedError("Simulation stopped")

                # Atualiza telemetria
                metrics = info["lane_metrics"]
                simulation_state["sim_time"] = info["sim_time"]
                simulation_state["avg_waiting_time"] = float(metrics.get("waiting_time_s", 0.0))
                simulation_state["south_queue"] = int(metrics.get("halting_vehicles", 0))
                simulation_state["phase"] = info.get("phase", "")
                simulation_state["reward"] = float(info.get("reward", 0.0))

                # Extrai os frames anotados do observer
                if hasattr(observer, "last_results") and observer.last_results:
                    for camera_id, res in observer.last_results.items():
                        try:
                            annotated = debugger.annotate(
                                res.frame, res.detections, res.tracks,
                                res.raw_counts, res.rois, res.queue_counts
                            )
                            _, buffer = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                            latest_frames[camera_id] = buffer.tobytes()
                        except Exception as e:
                            print(f"Erro ao anotar frame {camera_id}: {e}")

            try:
                # Environment.run() gerencia internamente: SumoClient, controller, encoder,
                # reward, run_episode — tudo encapsulado. Basta passar policy, observer e on_step.
                outcome, scenario = environment.run(
                    seed=201,
                    policy=policy,
                    observer=observer,
                    on_step=on_step,
                )
                print(f"Episódio concluído: {outcome.controlled_steps} steps controlados, "
                      f"recompensa média {outcome.mean_reward:.4f}")
            except InterruptedError:
                print("Episódio interrompido pelo usuário.")
            except Exception as e:
                print(f"Erro no episódio: {e}")
                import traceback
                traceback.print_exc()

            # Se apertaram Stop, volta pro while principal e aguarda

    finally:
        bridge.close()


@app.on_event("startup")
async def startup_event():
    global simulation_thread, should_stop
    should_stop = False
    simulation_thread = threading.Thread(target=run_simulation_loop, daemon=True)
    simulation_thread.start()

@app.on_event("shutdown")
async def shutdown_event():
    global should_stop
    should_stop = True

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.send_json(simulation_state)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        active_connections.remove(websocket)

@app.post("/api/control/{command}")
async def control_simulation(command: str):
    global simulation_state, inject_emergency_flag
    if command == "start":
        simulation_state["is_running"] = True
    elif command == "stop":
        simulation_state["is_running"] = False
    elif command == "inject_emergency":
        inject_emergency_flag = True
    
    for conn in active_connections:
        await conn.send_json(simulation_state)
        
    return {"status": "ok", "command": command}

async def video_stream_generator(camera_id: str):
    while True:
        frame_bytes = latest_frames.get(camera_id)
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        await asyncio.sleep(0.1) # 10fps limit

@app.get("/api/video/{camera_id}")
async def video_feed(camera_id: str):
    return StreamingResponse(video_stream_generator(camera_id), media_type="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
