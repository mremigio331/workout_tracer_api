from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class StravaCredentialsModel(BaseModel):
    token_type: str
    expires_at: int
    expires_in: int
    refresh_token: str
    access_token: str
