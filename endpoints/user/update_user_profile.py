from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from aws_lambda_powertools import Logger
from exceptions.user_exceptions import (
    InvalidUserIdException,
    UserNotFound,
    ProfileNotPublicOrDoesNotExist,
)
from pydantic import BaseModel, Field
from typing import Optional

from decorators.exceptions_decorator import exceptions_decorator
from helpers.jwt import decode_jwt, update_cognito_user_attributes
import os
from dynamodb.helpers.user_profile_helper import UserProfileHelper

logger = Logger(service="workout-tracer-api")
router = APIRouter()


class UpdateUserProfileRequest(BaseModel):
    email: Optional[str] = Field(None, description="The user's email address")
    name: Optional[str] = Field(None, description="The user's name")
    public_profile: Optional[bool] = Field(
        None, description="Whether the user's profile is public or private"
    )
    distance_unit: Optional[str] = Field(
        None, description="Distance unit for the user (e.g., Imperial, Metric)"
    )


@router.put("/profile", response_model=UpdateUserProfileRequest)
@exceptions_decorator
def update_user_profile(request: Request, user_profile: UpdateUserProfileRequest):
    """
    Update the user's profile information.
    """
    logger.append_keys(request_id=request.state.request_id)
    logger.info(f"Request body: {user_profile.dict()}")
    user_id = getattr(request.state, "user_token", None)
    logger.info(f"user_id from request.state.user_token: {user_id}")
    if not user_id:
        logger.warning("User ID not found in request state.")
        raise InvalidUserIdException("User ID not found in request.")

    try:
        # Use the module-level helper
        user_profile_helper = UserProfileHelper(request_id=request.state.request_id)
        updated_profile = user_profile_helper.update_user_profile_fields(
            user_id=user_id,
            name=user_profile.name,
            email=user_profile.email,
            public_profile=user_profile.public_profile,
            distance_unit=user_profile.distance_unit,
        )
        # Use dict() for Pydantic models, fallback to __dict__ for others
        if updated_profile:
            try:
                profile_dict = updated_profile.dict()
            except AttributeError:
                profile_dict = dict(updated_profile.__dict__)
            # Use jsonable_encoder to handle datetime serialization
            profile_dict = jsonable_encoder(profile_dict)
            logger.info(f"DynamoDB update result for user_id {user_id}: {profile_dict}")
        else:
            logger.warning(f"User with ID {user_id} not found in DynamoDB.")
            raise UserNotFound(f"User with ID {user_id} not found.")

        # Update Cognito user attributes (name and email)
        user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
        logger.info(
            f"Updating Cognito user attributes for user_id {user_id} in user_pool_id {user_pool_id}"
        )
        update_cognito_user_attributes(
            user_pool_id=user_pool_id,
            user_id=user_id,
            name=user_profile.name,
            email=user_profile.email,
        )
        logger.info(
            f"Successfully updated Cognito user attributes for user_id {user_id}"
        )

        return JSONResponse(status_code=200, content=profile_dict)

    except UserNotFound as e:
        logger.error(f"User not found: {e}")
        raise ProfileNotPublicOrDoesNotExist("Profile does not exist or is not public.")
