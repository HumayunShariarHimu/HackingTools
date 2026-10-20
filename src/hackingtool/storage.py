"""Atomic JSON writes: a failed/interrupted write must never truncate a good file."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_text(path: Path, text: str) -> None:
    """Write text to path atomically: temp file in the same dir, fsync, os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)          # atomic on POSIX; prior file survives any failure above
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json(path: Path, data: Any, **dumps_kwargs) -> None:
    """Serialize data to path atomically."""
    write_text(path, json.dumps(data, **dumps_kwargs))
