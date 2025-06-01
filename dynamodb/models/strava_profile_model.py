from pydantic import BaseModel
from typing import Optional, Any


class StravaAthleteModel(BaseModel):
    user_id: str
    username: Optional[str] = None
    resource_state: Optional[int] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    bio: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    sex: Optional[str] = None
    premium: Optional[bool] = None
    summit: Optional[bool] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    badge_type_id: Optional[int] = None
    weight: Optional[float] = None
    profile_medium: Optional[str] = None
    profile: Optional[str] = None
    friend: Optional[Any] = None
    follower: Optional[Any] = None
