from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from app.core.config import settings


def configure_telemetry(app: FastAPI) -> None:
    """Configure OpenTelemetry traces for FastAPI requests."""
    if settings.env in {"local", "development", "test"}:
        return
    endpoint = settings.clean_otel_exporter_otlp_endpoint
    if not endpoint or "localhost" in endpoint or "127.0.0.1" in endpoint:
        return
    resource = Resource.create({"service.name": settings.service_name, "deployment.environment": settings.env})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
