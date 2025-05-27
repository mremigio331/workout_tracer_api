from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response
from starlette.requests import Request
from urllib.parse import urlencode, urlparse, parse_qs
import os
import httpx

COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN", "")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID", "")
# Update redirect URI to port 5000
COGNITO_API_REDIRECT_URI = os.getenv("COGNITO_API_REDIRECT_URI")
COGNITO_AUTH_URL = f"{COGNITO_DOMAIN}/login?" + urlencode(
    {
        "client_id": COGNITO_CLIENT_ID,
        "response_type": "code",  # Use code flow
        "scope": "openid email profile",
        "redirect_uri": COGNITO_API_REDIRECT_URI,
    }
)


class CognitoAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only apply to /docs and root (for redirect)
        if request.url.path in ["/docs", "/"]:
            id_token = request.cookies.get("id_token")
            code = request.query_params.get("code")
            if not id_token and code:
                # Exchange code for tokens
                async with httpx.AsyncClient() as client:
                    token_resp = await client.post(
                        f"{COGNITO_DOMAIN}/oauth2/token",
                        data={
                            "grant_type": "authorization_code",
                            "client_id": COGNITO_CLIENT_ID,
                            "code": code,
                            "redirect_uri": COGNITO_API_REDIRECT_URI,
                        },
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                if token_resp.status_code == 200:
                    tokens = token_resp.json()
                    id_token = tokens.get("id_token")
                    if id_token:
                        response = RedirectResponse(url="/docs")
                        response.set_cookie("id_token", id_token, httponly=True)
                        return response
                # If token exchange fails, redirect to Cognito login
                return RedirectResponse(COGNITO_AUTH_URL)
            if request.url.path == "/docs" and not id_token:
                return RedirectResponse(COGNITO_AUTH_URL)
        return await call_next(request)
