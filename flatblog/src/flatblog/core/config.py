"""Load and access flatblog config.yaml."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def find_config(start: Path | None = None) -> Path:
    """Walk up from start (or cwd) to find config.yaml."""
    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / "config.yaml"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "No config.yaml found. Run `flatblog init` to create one."
    )


def load_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or find_config()
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f) or {}
    # Allow env-var override for api key
    if not cfg.get("ai", {}).get("api_key"):
        key = os.environ.get("FLATBLOG_AI_KEY", "")
        if key:
            cfg.setdefault("ai", {})["api_key"] = key
    return cfg


def save_config(cfg: dict[str, Any], path: Path | None = None) -> None:
    cfg_path = path or find_config()
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def repo_root(cfg_path: Path | None = None) -> Path:
    """Return the directory containing config.yaml."""
    return (cfg_path or find_config()).parent
