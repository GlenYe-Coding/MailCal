"""Atomic JSON file helpers used across the project."""
from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, payload, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
