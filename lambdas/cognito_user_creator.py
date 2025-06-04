import os
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities.typing import LambdaContext
from dynamodb.helpers.user_profile_helper import UserProfileHelper

logger = Logger(service="WorkoutTracer-Cognito-User-Creator")


@logger.inject_lambda_context
def handler(event: dict, context: LambdaContext) -> dict:
    logger.info("POST_CONFIRMATION Lambda triggered.")

    if event["triggerSource"] == "PostConfirmation_ConfirmSignUp":
        user_attrs = event["request"]["userAttributes"]
        logger.info(f"User attributes: {user_attrs}")

        user_id = user_attrs["sub"]
        email = user_attrs.get("email")
        name = user_attrs.get("name", "unknown")

        try:
            user_profile_helper = UserProfileHelper(request_id=context.aws_request_id)
            user_profile_helper.create_user_profile(
                user_id=user_id, email=email, name=name
            )
        except Exception as e:
            logger.error(f"Failed to create user profile: {e}")
            raise

    else:
        logger.warning(f"Unsupported triggerSource: {event['triggerSource']}")

    return event
