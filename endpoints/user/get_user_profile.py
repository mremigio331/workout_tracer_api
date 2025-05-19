from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from aws_lambda_powertools import Logger
from exceptions.user_exceptions import InvalidUserIdException, UserNotFound
from decorators.exceptions_decorator import exceptions_decorator
from clients.dynamo_client import WorkoutTracerDynamoDBClient

# Set up structured logger
logger = Logger(service="workout-tracer-api")

router = APIRouter()


@router.get("/profile", summary="Get a user profile", response_description="The user's profile")
@exceptions_decorator
async def get_user_profile(user_id: str):
    """
    Get User Profile Endpoint
    Returns:
        A JSON response containing the user's profile information.
    """
    logger.info("Getting request for user profile.")
    logger.info(f"User ID: {user_id}")
    if not user_id:
        raise InvalidUserIdException("User ID is required.")
    
    dynamo = WorkoutTracerDynamoDBClient()
    user_profile = dynamo.get_user_profile(user_id=user_id)
    if not user_profile:
        raise UserNotFound(f"User with ID {user_id} not found.")
    
    return JSONResponse(content={"user_profile": user_profile}, status_code=200)