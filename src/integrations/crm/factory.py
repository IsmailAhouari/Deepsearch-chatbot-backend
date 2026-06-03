"""CRM adapter factory — loads the configured adapter class at startup.

The adapter class is specified by `CRM_ADAPTER_CLASS` environment variable.
Default: `src.integrations.crm.null_adapter.NullAdapter`

If the class cannot be imported (e.g. package not installed), falls back to
NullAdapter with a WARNING log — this prevents a CRM misconfiguration from
blocking the entire application startup.
"""
from __future__ import annotations

import importlib

from src.core.logging import get_logger
from src.integrations.crm.base import CRMAdapter

logger = get_logger(__name__)

_cached_adapter: CRMAdapter | None = None


def get_crm_adapter() -> CRMAdapter:
    """Return (or create) the singleton CRM adapter instance.

    Loaded once at first call; subsequent calls return the cached instance.
    """
    global _cached_adapter
    if _cached_adapter is not None:
        return _cached_adapter

    from src.core.config import get_settings
    settings = get_settings()

    class_path = settings.crm_adapter_class
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        adapter_class = getattr(module, class_name)
        _cached_adapter = adapter_class()
        logger.info("crm_adapter_loaded", adapter=class_path)
    except Exception as exc:
        logger.warning(
            "crm_adapter_load_failed",
            adapter=class_path,
            error=str(exc),
            fallback="NullAdapter",
        )
        from src.integrations.crm.null_adapter import NullAdapter
        _cached_adapter = NullAdapter()

    return _cached_adapter
