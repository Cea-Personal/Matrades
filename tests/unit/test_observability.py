import logging

from fastapi.testclient import TestClient

from traderx.shared.observability import (
    TelemetryEvent,
    emit,
    metrics,
    record_data_freshness,
    record_queue_depth,
    register_alert_hook,
    register_telemetry_exporter,
    traced_operation,
    unregister_alert_hook,
    unregister_telemetry_exporter,
)
from traderx_api.main import app


class RecordingExporter:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []
        self.counters: list[tuple[str, int]] = []
        self.histograms: list[tuple[str, float]] = []

    def emit(self, event: TelemetryEvent) -> None:
        self.events.append(event)

    def counter(self, name: str, value: int) -> None:
        self.counters.append((name, value))

    def histogram(self, name: str, value: float) -> None:
        self.histograms.append((name, value))


def test_structured_redacted_telemetry_metrics_traces_and_alert_hooks(caplog) -> None:  # type: ignore[no-untyped-def]
    exporter = RecordingExporter()
    alerts: list[TelemetryEvent] = []
    register_telemetry_exporter(exporter)
    register_alert_hook(alerts.append)
    try:
        with caplog.at_level(logging.INFO, logger="traderx"):
            with traced_operation(
                "market.research",
                correlation_id="correlation-1",
                attributes={"api_token": "private", "category": "FOREX"},
            ):
                metrics.increment("research.candidates", 3)
            record_queue_depth("research", 4)
            record_data_freshness("mt5", 120, correlation_id="correlation-1")

        assert "private" not in caplog.text
        assert any(event.name == "market.research.started" for event in exporter.events)
        assert ("research.candidates", 3) in exporter.counters
        assert any(name == "queue.research.depth" for name, _ in exporter.histograms)
        assert alerts[-1].name == "data.freshness.exceeded"
        assert alerts[-1].correlation_id == "correlation-1"
    finally:
        unregister_alert_hook(alerts.append)
        unregister_telemetry_exporter(exporter)


def test_exporter_failure_never_breaks_the_observed_operation() -> None:
    class FailedExporter(RecordingExporter):
        def emit(self, event: TelemetryEvent) -> None:
            raise RuntimeError("collector unavailable")

    exporter = FailedExporter()
    register_telemetry_exporter(exporter)
    try:
        emit(TelemetryEvent("risk.decision", "correlation-2", {"decision": "BLOCKED"}))
    finally:
        unregister_telemetry_exporter(exporter)


def test_http_correlation_is_propagated_through_the_trace_boundary() -> None:
    response = TestClient(app).get(
        "/api/v1/health", headers={"X-Correlation-ID": "release-correlation-1"}
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "release-correlation-1"
    assert metrics.snapshot().counters["http.status.200"] >= 1
