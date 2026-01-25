"""Configuration management for Manus experiment."""
from pathlib import Path

DEFAULT_CONFIG = {
    "experiment": {
        "variant": "A1",
        "max_steps": 20,
        "task_id": "data_cleaning",
    },
    "model": {
        "name": "gpt-4o-mini",
        "tier": "flex",
    },
    "token_optimization": {
        "large_output_threshold": 150,
    },
    "paths": {
        "workspace": "workspace",
    },
}


def load_config(config_path: str | None = None) -> dict:
    if config_path and Path(config_path).exists():
        import yaml
        with open(config_path) as f:
            user_config = yaml.safe_load(f)
        return _merge_configs(DEFAULT_CONFIG, user_config)
    return DEFAULT_CONFIG


def _merge_configs(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value
    return result
