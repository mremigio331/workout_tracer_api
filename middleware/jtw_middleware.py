from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from helpers.jwt import decode_jwt
from aws_lambda_powertools import Logger

logger = Logger(service="workout-tracer-api")


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
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
            # If the request is for the docs, show a Swagger-friendly message
            if request.url.path == "/docs":
                from starlette.responses import HTMLResponse

                return HTMLResponse(
                    "<h2>Access Denied</h2><p>You do not have access to the API docs.</p>",
                    status_code=401,
                )
        request.state.user_token = token_user_id
        response = await call_next(request)
        return response
