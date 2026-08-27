from __future__ import annotations

from copy import deepcopy

from carmaker_recorder.config import AppConfig, config_from_dict, config_to_dict


def latest_config_dict(**overrides):
    raw = config_to_dict(AppConfig())
    for section, values in overrides.items():
        if section == "schema_version":
            raw[section] = values
        elif isinstance(values, dict):
            raw[section].update(deepcopy(values))
        else:
            raw[section] = deepcopy(values)
    return raw


def latest_config(**overrides):
    return config_from_dict(latest_config_dict(**overrides))
