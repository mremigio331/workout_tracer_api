from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from exceptions.user_exceptions import (
    InvalidUserIdException,
    UserNotFound,
    ProfileNotPublicOrDoesNotExist,
)
from decorators.exceptions_decorator import exceptions_decorator
from clients.dynamo_client import WorkoutTracerDynamoDBClient
from helpers.jwt import decode_jwt

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

    # Extract JWT from Authorization header and decode
    auth_header = request.headers.get("authorization")
    token_user_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            claims = decode_jwt(token)
            token_user_id = claims.get("sub")
        except Exception as e:
            logger.warning(f"JWT decode failed: {e}")
            token_user_id = None

    if not user_id:
        logger.warning("User ID not provided in request.")
        raise InvalidUserIdException("User ID is required.")

    if not token_user_id:
        logger.warning("Token User ID could not be extracted from JWT.")
        raise InvalidUserIdException("Token User ID is required.")

    dynamo = WorkoutTracerDynamoDBClient()
    user_profile_data = dynamo.get_user_profile(user_id=user_id)
    if not user_profile_data:
        logger.warning(f"User profile not found for user_id: {user_id}")
        raise UserNotFound(f"User with ID {user_id} not found.")

    # Interact with the raw dict
    public_profile = user_profile_data.get("public_profile")
    db_user_id = user_profile_data.get("PK").split(":")[1]

    logger.info(f"Public profile flag: {public_profile}")

    # If the user_id from the table matches the token user_id, return the profile
    if db_user_id == token_user_id:
        logger.info("Access granted: user is profile owner.")
        return JSONResponse(
            content={"user_profile": user_profile_data}, status_code=200
        )

    # If the profile is public, return the profile
    if public_profile is True:
        logger.info("Access granted: profile is public.")
        return JSONResponse(
            content={"user_profile": user_profile_data}, status_code=200
        )

    # Otherwise, access denied
    logger.info("Access denied: profile is not public and requester is not owner.")
    raise ProfileNotPublicOrDoesNotExist(
        "Access denied: profile is not public or does not exist."
    )
