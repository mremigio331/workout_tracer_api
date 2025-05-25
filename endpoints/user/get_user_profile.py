from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from exceptions.user_exceptions import InvalidUserIdException, UserNotFound
from decorators.exceptions_decorator import exceptions_decorator
from clients.dynamo_client import WorkoutTracerDynamoDBClient

logger = Logger(service="workout-tracer-api")
router = APIRouter()


@router.get(
    "/profile", summary="Get a user profile", response_description="The user's profile"
)
@exceptions_decorator
def get_user_profile(user_id: str, request: Request):
    """
    Get User Profile Endpoint
    Returns:
        A JSON response containing the user's profile information.
    """
    logger.info("Getting request for user profile.")
    logger.info(f"User ID: {user_id}")

    event = request.scope.get("aws.event")
    claims = None
    if event:
        claims = (
            event.get("requestContext", {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})
        )

    logger.info(f"Claims: {claims}")
    token_user_id = claims.get("sub") if claims else None

    logger.info(f"Token User ID: {token_user_id}")

    if not user_id or not token_user_id:
        raise InvalidUserIdException("User ID is required.")

    dynamo = WorkoutTracerDynamoDBClient()
    user_profile = dynamo.get_user_profile(user_id=user_id)
    if not user_profile:
        raise UserNotFound(f"User with ID {user_id} not found.")

    if user_profile.public_profile is False and user_id != token_user_id:
        raise UserNotFound(f"User with ID {user_id} not found.")

    return JSONResponse(content={"user_profile": user_profile}, status_code=200)
