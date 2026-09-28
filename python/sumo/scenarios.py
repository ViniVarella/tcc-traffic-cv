"""Seleção do cenário SUMO (arquivo .sumocfg) declarado no perfil YAML."""

from __future__ import annotations

from typing import Any


def resolve_sumo_scenario(config: dict[str, Any], scenario: str | None = None) -> tuple[str | None, str]:
    """Retorna ``(nome, caminho relativo do .sumocfg)`` para o cenário pedido.

    Perfis com ``sumo.scenarios`` usam ``scenario`` ou ``sumo.default_scenario``.
    Perfis legados com ``sumo.config_path`` não têm cenários nomeados.
    """
    sumo_config = config.get("sumo", {})
    scenarios = sumo_config.get("scenarios")
    if scenarios is None:
        if scenario is not None:
            raise ValueError(f"O perfil não declara sumo.scenarios; cenário {scenario!r} indisponível.")
        return None, str(sumo_config["config_path"])
    if "config_path" in sumo_config:
        raise ValueError("Use sumo.scenarios ou sumo.config_path, não ambos.")
    name = scenario if scenario is not None else sumo_config.get("default_scenario")
    if name not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise ValueError(f"Cenário SUMO {name!r} desconhecido. Disponíveis: {available}.")
    return str(name), str(scenarios[name])
