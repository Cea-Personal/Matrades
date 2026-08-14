from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from threading import Lock
from typing import Protocol, cast

from traderx.integrations.crypto import redact


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    name: str
    correlation_id: str | None
    attributes: dict[str, object]


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    counters: dict[str, int]
    timings_ms: dict[str, tuple[float, ...]]


class TelemetryExporter(Protocol):
    """Adapter boundary implemented by an OpenTelemetry OTLP exporter in deployment."""

    def emit(self, event: TelemetryEvent) -> None: ...

    def counter(self, name: str, value: int) -> None: ...

    def histogram(self, name: str, value: float) -> None: ...


class MetricRegistry:
    """Small exporter-neutral registry used by logs and an OpenTelemetry adapter."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._timings: dict[str, list[float]] = defaultdict(list)
        self._exporters: list[TelemetryExporter] = []

    def register_exporter(self, exporter: TelemetryExporter) -> None:
        self._exporters.append(exporter)

    def unregister_exporter(self, exporter: TelemetryExporter) -> None:
        if exporter in self._exporters:
            self._exporters.remove(exporter)

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value
        for exporter in tuple(self._exporters):
            _safe_export(partial(exporter.counter, name, value))

    def observe_ms(self, name: str, value: float) -> None:
        with self._lock:
            self._timings[name].append(value)
        for exporter in tuple(self._exporters):
            _safe_export(partial(exporter.histogram, name, value))

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            return MetricSnapshot(
                dict(self._counters), {key: tuple(value) for key, value in self._timings.items()}
            )


metrics = MetricRegistry()
_alert_hooks: list[Callable[[TelemetryEvent], None]] = []
_telemetry_exporters: list[TelemetryExporter] = []


def register_alert_hook(hook: Callable[[TelemetryEvent], None]) -> None:
    _alert_hooks.append(hook)


def unregister_alert_hook(hook: Callable[[TelemetryEvent], None]) -> None:
    if hook in _alert_hooks:
        _alert_hooks.remove(hook)


def register_telemetry_exporter(exporter: TelemetryExporter) -> None:
    """Attach an OTLP-compatible adapter without coupling domain code to an SDK."""

    _telemetry_exporters.append(exporter)
    metrics.register_exporter(exporter)


def unregister_telemetry_exporter(exporter: TelemetryExporter) -> None:
    if exporter in _telemetry_exporters:
        _telemetry_exporters.remove(exporter)
    metrics.unregister_exporter(exporter)


def emit(event: TelemetryEvent) -> None:
    """Structured, redacted seam for logs, traces, metrics, and alert exporters."""
    safe = TelemetryEvent(
        event.name,
        event.correlation_id,
        cast(dict[str, object], redact(event.attributes)),
    )
    logger = logging.getLogger("traderx")
    # Celery may disable loggers that already exist while it installs worker
    # logging. TraderX telemetry remains an application-owned audit signal in
    # API, worker, and combined test processes, so restore this namespace.
    logger.disabled = False
    logger.info(
        json.dumps(
            {
                "event": safe.name,
                "correlation_id": safe.correlation_id,
                "attributes": safe.attributes,
            },
            default=str,
            sort_keys=True,
        )
    )
    for exporter in tuple(_telemetry_exporters):
        _safe_export(partial(exporter.emit, safe))
    severity = str(safe.attributes.get("severity", "INFO"))
    if severity in {"HIGH", "CRITICAL"}:
        for hook in tuple(_alert_hooks):
            _safe_export(partial(hook, safe))


@contextmanager
def traced_operation(
    name: str, *, correlation_id: str | None, attributes: dict[str, object] | None = None
) -> Iterator[None]:
    """Emit an exporter-neutral span compatible with an OpenTelemetry bridge."""

    started = time.perf_counter()
    emit(TelemetryEvent(f"{name}.started", correlation_id, attributes or {}))
    try:
        yield
    except Exception as error:
        metrics.increment(f"{name}.failures")
        emit(
            TelemetryEvent(
                f"{name}.failed",
                correlation_id,
                {**(attributes or {}), "severity": "HIGH", "error_type": type(error).__name__},
            )
        )
        raise
    finally:
        duration = (time.perf_counter() - started) * 1000
        metrics.observe_ms(f"{name}.duration_ms", duration)
        emit(
            TelemetryEvent(
                f"{name}.finished",
                correlation_id,
                {**(attributes or {}), "duration_ms": round(duration, 3)},
            )
        )


def record_queue_depth(queue: str, depth: int) -> None:
    metrics.observe_ms(f"queue.{queue}.depth", float(depth))


def record_data_freshness(
    source: str, age_seconds: float, *, correlation_id: str | None = None
) -> None:
    metrics.observe_ms(f"freshness.{source}.seconds", age_seconds)
    if age_seconds > 90:
        emit(
            TelemetryEvent(
                "data.freshness.exceeded",
                correlation_id,
                {"source": source, "age_seconds": age_seconds, "severity": "HIGH"},
            )
        )


def _safe_export(action: Callable[[], None]) -> None:
    """Telemetry must never become a dependency of a financial safety decision."""

    try:
        action()
    except Exception:
        logging.getLogger("traderx.observability").exception("telemetry_export_failed")
