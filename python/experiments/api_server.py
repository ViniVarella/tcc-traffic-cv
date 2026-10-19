"""Painel web de demonstração: SUMO + Unity + visão ao vivo no navegador.

Com a Unity em Play Mode na cena SPImport:

    ../.venv/bin/python -m experiments.api_server

e abra http://127.0.0.1:8000/. Escolha cenário, versão e fonte da preempção e
clique em Iniciar. Só um SUMO por vez (porta TraCI 8873): não rode outro
experimento junto.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

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


# Classes COCO do detector genérico: carro, ônibus e caminhão. Motos (3) ficam
# de fora, como na demanda calibrada; não há classe de viatura.
GENERIC_CLASSES = "2,5,7"


def choose_detector(args: argparse.Namespace, argv: Sequence[str], generic: Path) -> bool:
    """Confere o detector; devolve True se caiu no genérico (COCO).

    O genérico só entra quando ``--model`` não foi passado e o detector ajustado
    padrão não existe; um ``--model`` explícito ausente encerra com erro, e um
    ``--classes`` explícito nunca é trocado.
    """
    if Path(args.model).exists():
        return False
    explicit = {item.split("=", 1)[0] for item in argv if item.startswith("--")}
    if "--model" in explicit or not generic.exists():
        raise SystemExit(f"Detector YOLO não encontrado: {args.model} (rode a partir de python/ ou passe --model).")
    print(f"aviso detector_ajustado_ausente={args.model} usando={generic.name} "
          "(sem detecção visual de ambulâncias; prioridade só pelo V2I)")
    args.model = str(generic)
    if "--classes" not in explicit:
        args.classes = GENERIC_CLASSES
    return True


def main() -> None:
    args = parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    generic = choose_detector(args, sys.argv[1:], base_dir / "yolov8n.pt")
    app = create_app(PanelSettings(base_dir, args, args.warmup_seconds, args.control_seconds, generic_detector=generic))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
