"""Path references persisted relative to the file that declares them."""

from __future__ import annotations

import os
from pathlib import Path


def relative_reference(owner: Path, target: Path) -> str:
    """Return a stable POSIX relative reference from ``owner``'s final location."""
    owner = Path(owner).resolve()
    target = Path(target).resolve()
    return Path(os.path.relpath(target, owner.parent)).as_posix()


def resolve_reference(owner: Path, value: str) -> Path:
    """Resolve a persisted path against its declaring file, retaining absolute refs."""
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = Path(owner).resolve().parent / candidate
    return candidate.resolve()
