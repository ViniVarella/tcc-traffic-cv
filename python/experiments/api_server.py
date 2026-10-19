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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    # Sem abreviações: "--mod"/"--class" não podem passar por --model/--classes.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    # Mesmo aquecimento das avaliações (compare_versions): a redução do painel compara
    # com elas. O aquecimento roda só no SUMO, sem a Unity, e leva poucos segundos.
    parser.add_argument("--warmup-seconds", type=float, default=300.0)
    parser.add_argument("--control-seconds", type=float, default=36000.0)
    parser.add_argument("--allow-generic-detector", action="store_true",
                        help="Sem o detector ajustado, usa o yolov8n.pt (COCO) local: sem detecção visual de ambulâncias.")
    add_vision_arguments(parser)
    parser.set_defaults(prime_seconds=5.0, send_interval=0.05, no_oracle_shadow=True)
    return parser.parse_args(argv)


# Classes COCO do detector genérico: carro, ônibus e caminhão. Motos (3) ficam
# de fora, como na demanda calibrada; não há classe de viatura.
GENERIC_CLASSES = "2,5,7"


def choose_detector(args: argparse.Namespace, argv: Sequence[str], generic: Path) -> bool:
    """Confere o detector; devolve True se caiu no genérico (COCO).

    O genérico só entra com ``--allow-generic-detector``, sem ``--model`` explícito e
    sem o detector ajustado padrão; nos outros casos, um detector ausente encerra
    com erro. Um ``--classes`` explícito nunca é trocado.
    """
    if Path(args.model).exists():
        return False
    explicit = {item.split("=", 1)[0] for item in argv if item.startswith("--")}
    if not args.allow_generic_detector or "--model" in explicit or not generic.exists():
        hint = "" if args.allow_generic_detector else "; para usar o yolov8n.pt genérico, passe --allow-generic-detector"
        raise SystemExit(f"Detector YOLO não encontrado: {args.model} (rode a partir de python/ ou passe --model{hint}).")
    print(f"aviso detector_ajustado_ausente={args.model} usando={generic.name} "
          "(sem detecção visual de ambulâncias; prioridade só pelo V2I)")
    args.model = str(generic)
    if "--classes" not in explicit:
        args.classes = GENERIC_CLASSES
    return True


class PanelServer(uvicorn.Server):
    """Uvicorn que avisa o painel ao receber Ctrl+C (ou Stop/Rerun do PyCharm).

    As câmeras (MJPEG) e a telemetria (WebSocket) são conexões contínuas: avisadas,
    elas terminam sozinhas e o encerramento não fica esperando por elas. O prazo
    de 2 s do uvicorn é só a garantia; depois dele o lifespan fecha o SUMO.
    """

    def handle_exit(self, sig: int, frame: object) -> None:
        self.config.app.state.runner.begin_shutdown()
        super().handle_exit(sig, frame)


def main() -> None:
    argv = sys.argv[1:]
    args = parse_args(argv)
    base_dir = Path(__file__).resolve().parents[1]
    generic = choose_detector(args, argv, base_dir / "yolov8n.pt")
    app = create_app(PanelSettings(base_dir, args, args.warmup_seconds, args.control_seconds, generic_detector=generic))
    PanelServer(uvicorn.Config(app, host=args.host, port=args.port, timeout_graceful_shutdown=2)).run()


if __name__ == "__main__":
    main()
