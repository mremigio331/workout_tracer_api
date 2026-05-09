import os
from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import Metrics, MetricUnit

logger = Logger(service="workout-tracer-api")

stage = os.environ.get("STAGE", "dev")
metrics = Metrics(
    namespace=f"WorkoutTracer-{stage.upper()}", service="workout-tracer-api"
)


def emit_metric(metric_name: str, dimensions: dict = None):
    """
    Emit a CloudWatch metric with optional dimensions.

    Args:
        metric_name: The name of the metric (e.g. "StravaApiCall").
        dimensions: Optional dict of dimension key-value pairs
                    (e.g. {"Endpoint": "/oauth/token"}).
    """
    try:
        if dimensions:
            for key, value in dimensions.items():
                metrics.add_dimension(name=key, value=str(value))
        metrics.add_metric(name=metric_name, unit=MetricUnit.Count, value=1)
        metrics.flush_metrics()
    except Exception as e:
        logger.warning(f"Failed to emit metric '{metric_name}': {e}")
