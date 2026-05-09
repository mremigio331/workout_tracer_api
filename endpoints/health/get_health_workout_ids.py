from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/workout-ids",
    summary="Get all Apple Health workout UUIDs",
    response_description="List of stored Apple Health workout UUID strings",
    tags=["AppleHealth"],
)
@exceptions_decorator
def get_health_workout_ids(request: Request):
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)
    workout_ids = helper.get_all_workout_ids(user_id=user_id)

    return JSONResponse(content={"workout_ids": workout_ids}, status_code=200)
