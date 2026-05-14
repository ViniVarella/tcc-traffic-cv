"""Teste manual de comunicacao Python -> Unity com JSON fake via UDP."""

from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any

import yaml

from bridge import SimulationState, TrafficLightState, UnityBridge, VehicleState


def load_config(config_path: Path) -> dict[str, Any]:
    """Carrega a configuracao YAML do projeto."""
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def build_fake_state(step: int) -> SimulationState:
    """Monta um estado fake simples para validar recepcao do step na Unity."""
    sim_time = round(step * 0.1, 2)
    vehicles = [
        VehicleState(
            id="veh_north_0",
            x=12.5 + step,
            y=0.0,
            z=34.0,
            angle=90.0,
            speed=8.5,
            type="passenger",
        ),
        VehicleState(
            id="veh_west_1",
            x=5.0,
            y=0.0,
            z=18.5 + step,
            angle=0.0,
            speed=6.0,
            type="passenger",
        ),
    ]
    traffic_lights = [
        TrafficLightState(
            id="Node2",
            phase=0 if step % 2 == 0 else 2,
            state="GGGGgrrrrrGGGGgrrrrr" if step % 2 == 0 else "rrrrrGGGGgrrrrrGGGGg",
        )
    ]
    return SimulationState(
        step=step,
        sim_time=sim_time,
        vehicles=vehicles,
        traffic_lights=traffic_lights,
    )


def main() -> None:
    """Envia alguns estados fake para a Unity usando host e porta do config."""
    base_dir = Path(__file__).resolve().parents[1]
    config = load_config(base_dir / "config.yaml")
    unity = UnityBridge.from_config(config)

    try:
        print(
            "Enviando estados fake para a Unity em "
            f"{unity.state_host}:{unity.state_port} via UDP."
        )
        print("Abra a Unity com um listener UDP para observar o step_id no log.")

        total_steps = 5
        for step in range(total_steps):
            state = build_fake_state(step)
            bytes_sent = unity.send_state(state)
            print(
                f"state_sent step={state.step} "
                f"step_id={state.step} "
                f"sim_time={state.sim_time:.2f} "
                f"vehicles={len(state.vehicles)} "
                f"traffic_lights={len(state.traffic_lights)} "
                f"bytes={bytes_sent}"
            )
            sleep(0.5)

        print("Envio concluido. Verifique se o step/step_id apareceu no log da Unity.")
    finally:
        unity.close()


if __name__ == "__main__":
    main()
