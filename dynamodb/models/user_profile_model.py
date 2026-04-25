from pydantic import BaseModel, EmailStr, validator
from datetime import datetime
from typing import Optional
from boto3.dynamodb.types import TypeDeserializer
import random


class UserProfileModel(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    created_at: str
    public_profile: bool = False
    beta_featues: bool = False
    provider: str = "Cognito"
    distance_unit: str = "Imperial"  # "Imperial" for miles/feet, "Metric" for km/m
    user_display_id: Optional[int] = None

    @validator("user_display_id", always=True, pre=True)
    def generate_display_id(cls, v):
        if v is None:
            return random.randint(1000000, 9999999)
        v = int(v)
        if not (1000000 <= v <= 9999999):
            raise ValueError(
                "user_display_id must be a 7-digit integer (1000000–9999999)"
            )
        return v

    @validator("distance_unit")
    def validate_distance_unit(cls, v):
        valid = {
            "imperial": "Imperial",
            "metric": "Metric",
            "Imperial": "Imperial",
            "Metric": "Metric",
            "miles": "Imperial",
            "Miles": "Imperial",
            "kilometers": "Metric",
            "Kilometers": "Metric",
        }
        if v not in valid:
            raise ValueError("distance_unit must be 'Imperial' or 'Metric'")
        return valid[v]
