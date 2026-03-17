"""
agent_jsonl.py
--------------
Helpers for writing agent workflow context as JSONL.
"""

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


def _serialise(value: Any) -> Any:
    """Convert dataclasses, Paths, and enums into JSON-safe values."""
    if is_dataclass(value):
        return {k: _serialise(v) for k, v in asdict(value).items()}
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(k): _serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialise(v) for v in value]
    return value


def append_jsonl(path: Path, record_type: str, payload: dict[str, Any]) -> None:
    """Append a single JSONL record to the target file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "type": record_type,
        "payload": _serialise(payload),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
