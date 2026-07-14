import logging
from dataclasses import dataclass

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import ObservabilitySettings

SERVICE_NAME = "github-devin-automation"


@dataclass(frozen=True, slots=True)
class Observability:
    """OpenTelemetry providers owned by the application process."""

    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider
    logging_handler: LoggingHandler
    previous_root_log_level: int

    def shutdown(self) -> None:
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.logging_handler)
        root_logger.setLevel(self.previous_root_log_level)
        self.logger_provider.shutdown()
        self.meter_provider.shutdown()
        self.tracer_provider.shutdown()


def configure_observability(
    app: FastAPI,
    settings: ObservabilitySettings,
) -> Observability | None:
    """Enable OTLP traces, metrics, and logs when an endpoint is configured."""
    if settings.otel_exporter_otlp_endpoint is None:
        return None

    endpoint = str(settings.otel_exporter_otlp_endpoint).rstrip("/")
    resource = Resource.create({"service.name": SERVICE_NAME})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{endpoint}/v1/logs"))
    )
    set_logger_provider(logger_provider)
    logging_handler = LoggingHandler(
        level=logging.NOTSET, logger_provider=logger_provider
    )
    root_logger = logging.getLogger()
    previous_root_log_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(logging_handler)

    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/api/health",
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    HTTPXClientInstrumentor().instrument(tracer_provider=tracer_provider)

    logging.getLogger(__name__).info("OpenTelemetry export enabled")
    return Observability(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        logging_handler=logging_handler,
        previous_root_log_level=previous_root_log_level,
    )
