from functools import wraps
from exceptions.user_exceptions import UserNotFound, InvalidUserIdException
from exceptions.jwt_exeptions import (
    InvalidJWTException,
    ExpiredJWTException,
    MissingJWTException,
    JWTSignatureException,
)
from fastapi.responses import JSONResponse
from botocore.exceptions import ClientError


def exceptions_decorator(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        # 4XX
        except UserNotFound as exc:
            return JSONResponse(
                content={"message": str(exc) or "User not found."}, status_code=404
            )
        except InvalidUserIdException as exc:
            return JSONResponse(
                content={"message": str(exc) or "Invalid user ID."}, status_code=400
            )
        except (InvalidJWTException, JWTSignatureException) as exc:
            return JSONResponse(
                content={"message": str(exc) or "Invalid JWT."}, status_code=401
            )
        except ExpiredJWTException as exc:
            return JSONResponse(
                content={"message": str(exc) or "JWT expired."}, status_code=401
            )
        except MissingJWTException as exc:
            return JSONResponse(
                content={"message": str(exc) or "JWT missing."}, status_code=401
            )

        ### 5XX
        except ClientError as exc:
            return JSONResponse(
                content={"message": str(exc) or "Internal server error."},
                status_code=500,
            )

    return wrapper
