# tests/unit/test_metrics_store.py
"""Unit tests for the metrics store (file-based JSON metrics)."""

from __future__ import annotations

import json
import tempfile

from app.screener.metrics_store import set_metric, get_metric, save_metrics, load_metrics


class TestMetricsStore:

    def test_set_and_get_metric(self, tmp_path):
        instance_path = str(tmp_path)
        set_metric(instance_path, "active_count", 42, namespace="screener")
        val = get_metric(instance_path, "active_count", namespace="screener")
        assert val == 42

    def test_get_missing_key_returns_default(self, tmp_path):
        instance_path = str(tmp_path)
        val = get_metric(instance_path, "missing", default=99, namespace="screener")
        assert val == 99

    def test_overwrite_metric(self, tmp_path):
        instance_path = str(tmp_path)
        set_metric(instance_path, "count", 10, namespace="test")
        set_metric(instance_path, "count", 20, namespace="test")
        assert get_metric(instance_path, "count", namespace="test") == 20

    def test_different_namespaces_independent(self, tmp_path):
        instance_path = str(tmp_path)
        set_metric(instance_path, "val", 1, namespace="ns1")
        set_metric(instance_path, "val", 2, namespace="ns2")
        assert get_metric(instance_path, "val", namespace="ns1") == 1
        assert get_metric(instance_path, "val", namespace="ns2") == 2

    def test_batch_save_and_load(self, tmp_path):
        instance_path = str(tmp_path)
        save_metrics(instance_path, {"a": 1, "b": 2, "c": 3}, namespace="test")
        result = load_metrics(instance_path, namespace="test")
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_atomic_write_creates_file(self, tmp_path):
        instance_path = str(tmp_path)
        set_metric(instance_path, "test", True, namespace="screener")
        path = tmp_path / "runtime_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["version"] == 1

    def test_corrupt_file_returns_defaults(self, tmp_path):
        instance_path = str(tmp_path)
        # Write corrupt data
        (tmp_path / "runtime_metrics.json").write_text("{{not valid json")
        val = get_metric(instance_path, "any", default="fallback", namespace="screener")
        assert val == "fallback"
