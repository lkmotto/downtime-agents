"""OpenTelemetry + Langfuse observability scaffolding.

Call ``init_observability()`` once at startup right before ``from motto_common.sentry_init import init_sentry``
(or right after it — order does not matter). Every LLM call wrapped in
``@traced`` (or manually with ``tracer.start_as_current_span``) is then visible
in Langfuse with cost, latency, prompt, and completion.

Environment (all optional):
    LANGFUSE_OTEL_ENDPOINT  — OTLP HTTP endpoint, defaults to Langfuse US cloud.
    LANGFUSE_PUBLIC_KEY     — Langfuse public key (used for Basic auth).
    LANGFUSE_SECRET_KEY     — Langfuse secret key (used for Basic auth).

When ``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are both set the SDK
sends authenticated traces. If they are missing the exporter still starts but
will receive unauthenticated requests (Langfuse will reject them).
"""

from __future__ import annotations

from motto_common.sentry_init import init_sentry  # was: import sentry_init

init_sentry(agent_name="downtime-email-agent")

import os
from base64 import b64encode

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def _basic_auth_header(k: str, s: str) -> dict[str, str]:
    """Build an RFC 7617 Basic auth header from a key/secret pair."""
    colon = chr(58)
    token = b64encode((k + colon + s).encode()).decode()
    return {"Authorization": "Basic " + token}


def init_observability(service_name: str = "downtime-email-agent") -> trace.Tracer:
    """Initialise OTel tracing pointed at Langfuse. Idempotent — safe to
    call more than once."""
    if trace.get_tracer_provider().__class__.__name__ == "TracerProvider":
        return trace.get_tracer(service_name)

    endpoint = os.getenv(
        "LANGFUSE_OTEL_ENDPOINT",
        "https://us.cloud.langfuse.com/api/public/otel/v1/traces",
    )
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    headers: dict[str, str] = {}
    if public_key and secret_key:
        headers = _basic_auth_header(public_key, secret_key)

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
