from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper
import base64
import json
import urllib.parse

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/workouts",
    summary="Get all Apple Health workouts with pagination",
    response_description="Paginated list of Apple Health workouts",
    tags=["AppleHealth"],
)
@exceptions_decorator
def get_health_workouts(
    request: Request,
    limit: int = Query(
        500, ge=1, le=500, description="Number of workouts to return (max 500)"
    ),
    next_token: str = Query(None, description="Token for fetching the next page"),
):
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)

    dynamo_next_token = None
    if next_token:
        try:
            decoded_url_token = urllib.parse.unquote(next_token)
            dynamo_next_token = json.loads(
                base64.urlsafe_b64decode(decoded_url_token.encode()).decode()
            )
        except Exception as e:
            logger.warning(
                f"Invalid next_token provided ('{next_token}'): {e}. Defaulting to None"
            )
            dynamo_next_token = None

    # Project only the fields needed for dashboard display.
    # "name" and "locations" are not reserved words in DynamoDB but we alias
    # "name" to be safe since it is a reserved word.
    result = helper.get_all_workouts(
        user_id=user_id,
        limit=limit,
        next_token=dynamo_next_token,
        projection_expression=(
            "workout_uuid, #n, workout_activity_type, start_date, "
            "total_distance, duration, total_energy_burned, elevation_ascended, "
            "summary_polyline, average_speed, average_heartrate, max_heartrate, "
            "locations"
        ),
        expression_attribute_names={
            "#n": "name",
        },
    )

    workouts = result.get("workouts", [])
    returned_next_token = result.get("next_token")

    if returned_next_token:
        new_next_token = base64.urlsafe_b64encode(
            json.dumps(returned_next_token).encode()
        ).decode()
    else:
        new_next_token = None

    return JSONResponse(
        content={
            "limit": limit,
            "next_token": new_next_token,
            "workouts": workouts,
        },
        status_code=200,
    )
