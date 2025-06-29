from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from boto3.dynamodb.types import TypeDeserializer


class UserProfileModel(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    created_at: str
    public_profile: bool = False
    beta_featues: bool = False
