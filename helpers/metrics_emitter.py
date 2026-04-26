from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import Metrics, MetricUnit
import os

logger = Logger(service="workout-tracer-api")

metrics = Metrics(namespace="WorkoutTracer/Workouts", service="workout-tracer-api")


def emit_metric(metric_name: str, dimensions: dict, value: float = 1) -> None:
    """Emit a CloudWatch metric via EMF.

    Automatically adds Stage dimension from STAGE env var.
    Catches and logs any emission errors without raising.

    Args:
        metric_name: The name of the CloudWatch metric.
        dimensions: Dictionary of dimension name/value pairs.
        value: Numeric value for the metric (defaults to 1).
    """
    try:
        stage = os.environ.get("STAGE", "Dev")
        metrics.add_dimension(name="Stage", value=stage)
        for dim_name, dim_value in dimensions.items():
            metrics.add_dimension(name=dim_name, value=dim_value)
        metrics.add_metric(name=metric_name, unit=MetricUnit.Count, value=value)
        metrics.flush_metrics()
    except Exception as e:
        logger.error(f"Failed to emit metric {metric_name}: {e}")
