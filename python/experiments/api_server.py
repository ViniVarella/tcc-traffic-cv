"""Painel web de demonstração: SUMO + Unity + visão ao vivo no navegador.

Com a Unity em Play Mode na cena SPImport:

    ../.venv/bin/python -m experiments.api_server

e abra http://127.0.0.1:8000/. Escolha cenário, versão e fonte da preempção e
clique em Iniciar. Só um SUMO por vez (porta TraCI 8873): não rode outro
experimento junto.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from dashboard.app import PanelSettings, create_app
from experiments.visual_observer import add_vision_arguments


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--warmup-seconds", type=float, default=30.0)
    parser.add_argument("--control-seconds", type=float, default=36000.0)
    add_vision_arguments(parser)
    parser.set_defaults(prime_seconds=5.0, send_interval=0.05, no_oracle_shadow=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = Path(args.model)
    if not model.exists():
        # Fallback para o yolov8n.pt local se o detector customizado não estiver presente
        local_yolo = Path(__file__).resolve().parents[1] / "yolov8n.pt"
        if local_yolo.exists():
            print(f"Aviso: detector ajustado ({model}) não encontrado.")
            print(f"Utilizando modelo local de fallback: {local_yolo.name} com classes COCO (2,3,5,7).")
            args.model = str(local_yolo)
            args.classes = "2,3,5,7"
            model = local_yolo
        else:
            raise SystemExit(f"Detector YOLO não encontrado: {model} (rode a partir de python/ ou passe --model).")
    base_dir = Path(__file__).resolve().parents[1]
    app = create_app(PanelSettings(base_dir, args, args.warmup_seconds, args.control_seconds))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
