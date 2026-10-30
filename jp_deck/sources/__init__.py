"""Finite source-adapter selection at the runtime boundary."""

from __future__ import annotations

from types import ModuleType

_REGISTERED_ADAPTERS = {"tango-n1-mimi-n1-v1"}


def is_registered_adapter(adapter_id: str) -> bool:
    return adapter_id in _REGISTERED_ADAPTERS


def get_source_adapter(adapter_id: str) -> ModuleType:
    if adapter_id == "tango-n1-mimi-n1-v1":
        from .tango_n1_mimi import adapter

        return adapter
    raise ValueError(f"Unsupported source adapter profile {adapter_id!r}")
