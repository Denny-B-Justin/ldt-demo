"""
memo.py
================
A tiny bounded, key-addressable memo for expensive-but-deterministic results
(assembled analytics payloads, built Plotly figures, rendered tab content).

The underlying datasets only change on a data-release cadence, so within a
release every ``(country, tab, year, province, municipality, metric, theme)``
combination maps to exactly one answer. Computing it once per worker and
replaying it turns a repeated filter change or tab switch from "rebuild
everything" into a dict lookup.

Every memo created here registers its ``clear`` with :mod:`datastore`, so a
background warm / manual refresh flushes stale entries automatically.
"""

from __future__ import annotations

import functools
import json
import threading
from collections import OrderedDict
from typing import Any, Callable

_ALL_CLEARS = []


def _key(args: tuple, kwargs: dict) -> str:
    return json.dumps([args, kwargs], sort_keys=True, default=str)


def keyed_memo(maxsize: int = 128) -> Callable:
    """Decorator: bounded LRU memo keyed by a JSON dump of the call arguments
    (so unhashable dict/list arguments are fine)."""

    def decorator(fn: Callable) -> Callable:
        store: "OrderedDict[str, Any]" = OrderedDict()
        lock = threading.Lock()

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            k = _key(args, kwargs)
            with lock:
                if k in store:
                    store.move_to_end(k)
                    return store[k]
            value = fn(*args, **kwargs)
            with lock:
                store[k] = value
                store.move_to_end(k)
                while len(store) > maxsize:
                    store.popitem(last=False)
            return value

        def clear() -> None:
            with lock:
                store.clear()

        wrapper.cache_clear = clear  # type: ignore[attr-defined]
        _ALL_CLEARS.append(clear)
        return wrapper

    return decorator


def clear_all() -> None:
    for clear in list(_ALL_CLEARS):
        try:
            clear()
        except Exception:  # noqa: BLE001
            pass


try:  # register with the data layer so a warm flushes every memo
    import datastore

    datastore.register_invalidation_hook(clear_all)
except Exception:  # noqa: BLE001 - datastore optional (e.g. in isolated tests)
    pass
