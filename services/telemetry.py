import os
import app.config as cfg

def init_telemetry():
    """Initializes Arize Phoenix and OpenTelemetry instrumentation if enabled."""
    if cfg.ENABLE_TELEMETRY == "true":
        print("🚀 Initializing Arize Phoenix Telemetry...")
        try:
            import phoenix as px
            from openinference.instrumentation.langchain import LangChainInstrumentor
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            # Start the Phoenix local app server (defaulting to port 6006)
            px.launch_app(port=6006)

            # Configure OpenTelemetry exporter pointing to the local Phoenix receiver
            tracer_provider = TracerProvider()
            tracer_provider.add_span_processor(
                SimpleSpanProcessor(OTLPSpanExporter(endpoint=cfg.TELEMETRY_ENDPOINT))
            )
            trace.set_tracer_provider(tracer_provider)

            # Auto-instrument LangChain & LangGraph
            LangChainInstrumentor().instrument()
            print(f"✨ Telemetry successfully active on {cfg.TELEMETRY_ENDPOINT}")
        except ImportError as e:
            print(f"[Warning] Telemetry dependencies missing: {e}. Run 'pip install arize-phoenix openinference-instrumentation-langchain' to enable.")
        except Exception as e:
            print(f"[Warning] Telemetry failed to initialize: {e}. Skipping tracing.")
