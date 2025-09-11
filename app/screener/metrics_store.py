# app/screener/metrics_store.py
# Simple namespaced JSON metrics store (atomic writes), lives in instance/.
# Use set_metric/get_metric for single values or save_metrics/load_metrics for batches.

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

FILENAME = "runtime_metrics.json"

def _path(instance_path: str, filename: str = FILENAME) -> Path:
    return Path(instance_path) / filename

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _empty_doc() -> Dict[str, Any]:
    return {"version": 1, "namespaces": {}}

def _load_all(instance_path: str, filename: str = FILENAME) -> Dict[str, Any]:
    try:
        with open(_path(instance_path, filename), "r", encoding="utf-8") as f:
            return json.load(f) or _empty_doc()
    except Exception:
        return _empty_doc()

def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)

def save_metrics(instance_path: str, updates: Dict[str, Any], *,
                 namespace: str = "default", filename: str = FILENAME) -> None:
    """
    Merge `updates` into the given namespace, stamping updated_at per key.
    """
    doc = _load_all(instance_path, filename)
    ns = doc.setdefault("namespaces", {}).setdefault(namespace, {})
    stamp = _now_iso()
    for k, v in updates.items():
        ns[k] = {"value": v, "updated_at": stamp}
    _atomic_write(_path(instance_path, filename), doc)

def set_metric(instance_path: str, key: str, value: Any, *,
               namespace: str = "default", filename: str = FILENAME) -> None:
    save_metrics(instance_path, {key: value}, namespace=namespace, filename=filename)

def load_metrics(instance_path: str, *, namespace: str = "default",
                 filename: str = FILENAME) -> Dict[str, Any]:
    """
    Return {key: value} dict for the namespace (values only).
    """
    doc = _load_all(instance_path, filename)
    ns = doc.get("namespaces", {}).get(namespace, {}) or {}
    return {k: (v.get("value") if isinstance(v, dict) else v) for k, v in ns.items()}

def get_metric(instance_path: str, key: str, default: Any = None, *,
               namespace: str = "default", filename: str = FILENAME) -> Any:
    ns = load_metrics(instance_path, namespace=namespace, filename=filename)
    return ns.get(key, default)


def get_metric_age_sec(instance_path: str, key: str, *,
                       namespace: str = "default", filename: str = FILENAME) -> float | None:
    """Return seconds since *key* was last updated, or None if missing."""
    doc = _load_all(instance_path, filename)
    ns = doc.get("namespaces", {}).get(namespace, {}) or {}
    entry = ns.get(key)
    if not isinstance(entry, dict) or "updated_at" not in entry:
        return None
    try:
        ts = datetime.fromisoformat(entry["updated_at"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except (ValueError, TypeError):
        return None
