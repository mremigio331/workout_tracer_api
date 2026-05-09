from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper
from aws_lambda_powertools.metrics import Metrics, MetricUnit
from typing import List
import os

logger = Logger(service="workout-tracer-api")
router = APIRouter()

stage = os.environ.get("STAGE", "dev")
metrics = Metrics(
    namespace=f"WorkoutTracer-{stage.upper()}", service="workout-tracer-api"
)

MAX_BATCH_SIZE = 100


@router.post(
    "/import",
    summary="Import Apple Health workouts",
    response_description="Import results with created, updated, and error counts",
    tags=["AppleHealth"],
)
@exceptions_decorator
def import_health_workouts(request: Request, payloads: List[dict]):
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    if len(payloads) > MAX_BATCH_SIZE:
        logger.warning(
            f"Batch size {len(payloads)} exceeds maximum of {MAX_BATCH_SIZE}."
        )
        return JSONResponse(
            content={
                "error": f"Batch size exceeds maximum of {MAX_BATCH_SIZE} workouts per request."
            },
            status_code=400,
        )

    helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)

    created = 0
    updated = 0
    errors = 0

    for workout_data in payloads:
        try:
            _, action = helper.put_apple_health_workout(
                user_id=user_id, workout_data=workout_data
            )
            if action == "create":
                created += 1
                metrics.add_dimension(name="SourceType", value="AppleHealth")
                metrics.add_metric(
                    name="WorkoutCreated", unit=MetricUnit.Count, value=1
                )
                metrics.flush_metrics()
            elif action == "update":
                updated += 1
                metrics.add_dimension(name="SourceType", value="AppleHealth")
                metrics.add_metric(
                    name="WorkoutUpdated", unit=MetricUnit.Count, value=1
                )
                metrics.flush_metrics()
        except Exception as e:
            errors += 1
            logger.error(f"Failed to import workout for user_id={user_id}: {e}")

    return JSONResponse(
        content={"created": created, "updated": updated, "errors": errors},
        status_code=200,
    )
