"""Resume o domain gap visão × oráculo TraCI a partir do log de ``run_visual_policy``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from controller import DqnAgent
from vision import build_state_encoder
from vision.lane_feature_evaluation import action_agreement, feature_gap, ground_offset_estimate


def parse_args(base_dir: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mede erros das features visuais contra o oráculo TraCI.")
    parser.add_argument("--config", type=Path, default=base_dir / "configs" / "sp.yaml")
    parser.add_argument("--step-log", type=Path, action="append", required=True, help="JSONL de run_visual_policy (repetível).")
    parser.add_argument("--dqn-model", type=Path, default=None, help="Checkpoint v2 para medir a concordância de ações.")
    parser.add_argument("--output", type=Path, default=base_dir.parent / "results" / "evaluation" / "lane-feature-gap.json")
    return parser.parse_args()


def main() -> None:
    base_dir = Path(__file__).resolve().parents[1]
    args = parse_args(base_dir)
    records: list[dict[str, Any]] = []
    for path in args.step_log:
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if not records:
        raise ValueError("Nenhum step registrado nos logs informados.")
    if all(record.get("oracle") is None for record in records):
        raise ValueError("Os logs não têm o oráculo em paralelo; rode run_visual_policy sem --no-oracle-shadow.")
    report: dict[str, Any] = {
        "steps": len(records),
        "steps_without_vision": sum(record.get("visual") is None for record in records),
        "features": feature_gap(records),
        "ground_offset": ground_offset_estimate(records),
    }
    if args.dqn_model is not None:
        config = yaml.safe_load(args.config.resolve().read_text(encoding="utf-8"))
        agent = DqnAgent.load(args.dqn_model, device="cpu")
        report["action_agreement"] = action_agreement(records, agent.q_values, build_state_encoder(config, agent.config.state_version))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"lane_gap steps={report['steps']} steps_without_vision={report['steps_without_vision']}")
    for lane, features in report["features"].items():
        cells = " ".join(f"{name}:mae={values['mae']:.2f},bias={values['bias']:+.2f}" for name, values in features.items())
        print(f"lane_gap {lane} {cells}")
    for camera, values in report["ground_offset"].items():
        offset = values["median_offset_m"]
        print(f"ground_offset {camera} matches={values['matches']} median_offset_m={'n/a' if offset is None else f'{offset:+.2f}'}")
    if "action_agreement" in report:
        agreement = report["action_agreement"]
        rate = agreement["agreement_rate"]
        print(f"action_agreement decisions={agreement['decisions']} agreement_rate={'n/a' if rate is None else f'{rate:.3f}'}")
    print(f"lane_gap_complete output={args.output}")


if __name__ == "__main__":
    main()
