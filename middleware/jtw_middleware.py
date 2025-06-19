from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from helpers.jwt import decode_jwt
from aws_lambda_powertools import Logger

logger = Logger(service="workout-tracer-api")


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.append_keys(
            request_id=request.state.request_id,
        )
        logger.info(f"JWTMiddleware: Path={request.url.path} Method={request.method}")
        auth_header = request.headers.get("authorization")
        token_user_id = None
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            logger.info("Authorization header found, attempting to decode JWT.")
            try:
                claims = decode_jwt(token)
                token_user_id = claims.get("sub")
                logger.info(f"JWT decoded successfully. sub: {token_user_id}")
            except Exception as e:
                logger.warning(f"JWT decode failed: {e}")
        else:
            logger.info("No valid Authorization header found.")
        if not token_user_id:
            logger.warning(f"No valid user token for path {request.url.path}")
            # If the request is for the docs, show a Swagger-friendly message
            if request.url.path == "/docs":
                from starlette.responses import HTMLResponse

                logger.info("Returning Swagger-friendly 401 HTML response for /docs")
                return HTMLResponse(
                    "<h2>Access Denied</h2><p>You do not have access to the API docs.</p>",
                    status_code=401,
                )
        request.state.user_token = token_user_id
        response = await call_next(request)
        logger.info(f"Response status for {request.url.path}: {getattr(response, 'status_code', 'unknown')}")
        return response
