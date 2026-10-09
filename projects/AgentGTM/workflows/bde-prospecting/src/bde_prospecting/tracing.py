"""Optional Arize Phoenix tracing.

Set PHOENIX_COLLECTOR_ENDPOINT (e.g. http://localhost:6006) and install the `tracing`
extra. Every Claude call is then traced automatically, and each command run is a span.
"""

import contextlib
import logging
import os

log = logging.getLogger(__name__)
_tracer = None


def setup():
    global _tracer
    if not os.environ.get("PHOENIX_COLLECTOR_ENDPOINT"):
        return
    try:
        from opentelemetry import trace
        from phoenix.otel import register
    except ImportError:
        log.warning("PHOENIX_COLLECTOR_ENDPOINT is set but the tracing extra isn't installed: pip install -e '.[tracing]'")
        return
    register(project_name=os.environ.get("PHOENIX_PROJECT_NAME", "agentgtm-bde-prospecting"), auto_instrument=True)
    _tracer = trace.get_tracer("bde_prospecting")


@contextlib.contextmanager
def span(name, **attributes):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)
        yield s
