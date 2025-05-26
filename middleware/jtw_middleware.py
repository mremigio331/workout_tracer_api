from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from helpers.jwt import decode_jwt
from aws_lambda_powertools import Logger

logger = Logger(service="workout-tracer-api")

class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Log all headers as seen by JWT middleware
        auth_header = request.headers.get("authorization")
        token_user_id = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                claims = decode_jwt(token)
                token_user_id = claims.get("sub")
            except Exception as e:
                logger.warning(f"JWT decode failed: {e}")
        if not token_user_id:
            raise HTTPException(
                status_code=401,
                detail="Token not found or invalid. User does not have access."
            )
        request.state.user_token = token_user_id
        response = await call_next(request)
        return response

