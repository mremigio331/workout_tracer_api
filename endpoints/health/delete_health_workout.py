from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from decorators.exceptions_decorator import exceptions_decorator
from dynamodb.helpers.apple_health_workout_helper import AppleHealthWorkoutHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.delete(
    "/workout/{workout_uuid}",
    summary="Delete an Apple Health workout",
    response_description="Deletion result",
    tags=["AppleHealth"],
)
@exceptions_decorator
def delete_health_workout(request: Request, workout_uuid: str):
    user_id = getattr(request.state, "user_token", None)
    if not user_id:
        logger.warning("User ID not found in request state.")
        return JSONResponse(
            content={"error": "User ID not found in request."}, status_code=400
        )

    helper = AppleHealthWorkoutHelper(request_id=request.state.request_id)
    deleted = helper.delete_apple_health_workout(
        user_id=user_id, workout_uuid=workout_uuid
    )

    if deleted:
        return JSONResponse(
            content={"message": f"Workout {workout_uuid} deleted successfully."},
            status_code=200,
        )
    else:
        return JSONResponse(
            content={"error": f"Workout {workout_uuid} not found."},
            status_code=404,
        )
