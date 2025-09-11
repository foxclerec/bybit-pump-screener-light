# tests/integration/test_sse_stream.py
"""Integration tests for the SSE signal stream endpoint."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone

import httpx
import pytest

from app.extensions import db
from app.models import Signal, DetectionRule


@pytest.mark.usefixtures("db_session")
class TestSSEStream:

    @pytest.fixture(scope="class")
    def sse_server(self, app):
        """Run Flask app on a background thread for SSE tests."""
        host, port = "127.0.0.1", 5198
        server = None

        def run():
            nonlocal server
            from werkzeug.serving import make_server
            server = make_server(host, port, app, threaded=True)
            server.serve_forever()

        t = threading.Thread(target=run, daemon=True)
        t.start()

        for _ in range(20):
            try:
                httpx.get(f"http://{host}:{port}/api/ping", timeout=1.0)
                break
            except Exception:
                time.sleep(0.2)

        yield f"http://{host}:{port}"

        if server:
            server.shutdown()

    def test_stream_sends_new_signal(self, app, sse_server):
        """New signal inserted into DB is pushed via SSE within 3 seconds."""
        base_url = sse_server

        with app.app_context():
            Signal.query.delete()
            db.session.commit()

        received = []

        def listen_sse():
            try:
                with httpx.stream("GET", f"{base_url}/api/signals/stream", timeout=5.0) as resp:
                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            received.append(data)
                            return
            except Exception:
                pass

        listener = threading.Thread(target=listen_sse, daemon=True)
        listener.start()
        time.sleep(0.5)

        with app.app_context():
            rule = DetectionRule.query.first()
            sig = Signal(
                exchange="bybit",
                symbol="SSETEST",
                rule_id=rule.id,
                change_pct=5.0,
                window="2m",
                price=100.0,
                event_ts=datetime.now(timezone.utc),
            )
            db.session.add(sig)
            db.session.commit()

        listener.join(timeout=4.0)

        assert len(received) >= 1, "SSE should deliver signal within 3 seconds"
        assert received[0]["symbol"] == "SSETEST"
        assert received[0]["pct"] == 5.0

    def test_stream_latency_under_3_seconds(self, app, sse_server):
        """Signal should appear in SSE stream within 3 seconds of DB insert."""
        base_url = sse_server

        with app.app_context():
            Signal.query.delete()
            db.session.commit()

        received_at = []

        def listen_sse():
            try:
                with httpx.stream("GET", f"{base_url}/api/signals/stream", timeout=5.0) as resp:
                    for line in resp.iter_lines():
                        if line.startswith("data: "):
                            received_at.append(time.time())
                            return
            except Exception:
                pass

        listener = threading.Thread(target=listen_sse, daemon=True)
        listener.start()
        time.sleep(0.5)

        insert_time = time.time()
        with app.app_context():
            rule = DetectionRule.query.first()
            db.session.add(Signal(
                exchange="bybit", symbol="LATTEST", rule_id=rule.id,
                change_pct=3.0, window="2m", price=50.0,
                event_ts=datetime.now(timezone.utc),
            ))
            db.session.commit()

        listener.join(timeout=4.0)

        assert len(received_at) >= 1
        latency = received_at[0] - insert_time
        assert latency < 3.0, f"SSE latency was {latency:.2f}s, expected < 3s"
