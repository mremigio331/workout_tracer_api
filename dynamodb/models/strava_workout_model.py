from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class StravaMapModel(BaseModel):
    id: Optional[str] = None
    summary_polyline: Optional[str] = None
    polyline: Optional[str] = None
    resource_state: Optional[int] = None


class StravaAthleteModel(BaseModel):
    id: Optional[int]
    resource_state: Optional[int]


class SegmentModel(BaseModel):
    id: Optional[int]
    resource_state: Optional[int]
    name: Optional[str]
    activity_type: Optional[str]
    distance: Optional[float]
    average_grade: Optional[float]
    maximum_grade: Optional[float]
    elevation_high: Optional[float]
    elevation_low: Optional[float]
    start_latlng: Optional[List[float]]
    end_latlng: Optional[List[float]]
    climb_category: Optional[int]
    city: Optional[str]
    state: Optional[str]
    country: Optional[str]
    private: Optional[bool]
    hazardous: Optional[bool]
    starred: Optional[bool]


class SegmentEffortModel(BaseModel):
    id: Optional[int]
    resource_state: Optional[int]
    name: Optional[str]
    activity: Optional[Dict[str, Any]]
    athlete: Optional[Dict[str, Any]]
    elapsed_time: Optional[int]
    moving_time: Optional[int]
    start_date: Optional[str]
    start_date_local: Optional[str]
    distance: Optional[float]
    start_index: Optional[int]
    end_index: Optional[int]
    average_cadence: Optional[float] = None
    device_watts: Optional[bool]
    average_watts: Optional[float] = None
    segment: Optional[SegmentModel]
    kom_rank: Optional[int] = None  # <-- must be Optional with default None
    pr_rank: Optional[int] = None
    achievements: Optional[List[Any]]
    hidden: Optional[bool]


class LapModel(BaseModel):
    id: Optional[int]
    resource_state: Optional[int]
    name: Optional[str]
    activity: Optional[Dict[str, Any]]
    athlete: Optional[Dict[str, Any]]
    elapsed_time: Optional[int]
    moving_time: Optional[int]
    start_date: Optional[str]
    start_date_local: Optional[str]
    distance: Optional[float]
    start_index: Optional[int]
    end_index: Optional[int]
    total_elevation_gain: Optional[float]
    average_speed: Optional[float]
    max_speed: Optional[float]
    average_cadence: Optional[float] = None
    device_watts: Optional[bool]
    average_watts: Optional[float] = None
    lap_index: Optional[int]
    split: Optional[int]


class GearModel(BaseModel):
    id: Optional[str]
    primary: Optional[bool]
    name: Optional[str]
    resource_state: Optional[int]
    distance: Optional[float]


class PhotoUrlModel(BaseModel):
    urls: Optional[Dict[str, str]]


class PhotoPrimaryModel(BaseModel):
    id: Optional[int] = None
    unique_id: Optional[str]
    urls: Optional[Dict[str, str]]
    source: Optional[int]
    media_type: Optional[int]


class PhotosModel(BaseModel):
    primary: Optional[PhotoPrimaryModel] = None
    use_primary_photo: Optional[bool] = None
    count: Optional[int] = None


class HighlightedKudoserModel(BaseModel):
    destination_url: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    show_name: Optional[bool] = None


class StravaWorkoutModel(BaseModel):
    resource_state: Optional[int] = None
    athlete: Optional[StravaAthleteModel] = None
    name: Optional[str] = None
    distance: Optional[float] = None
    moving_time: Optional[int] = None
    elapsed_time: Optional[int] = None
    total_elevation_gain: Optional[float] = None
    type: Optional[str] = None
    sport_type: Optional[str] = None
    workout_type: Optional[int] = None
    id: Optional[int]
    start_date: Optional[str] = None
    start_date_local: Optional[str] = None
    timezone: Optional[str] = None
    utc_offset: Optional[float] = None
    location_city: Optional[str] = None
    location_state: Optional[str] = None
    location_country: Optional[str] = None
    achievement_count: Optional[int] = None
    kudos_count: Optional[int] = None
    comment_count: Optional[int] = None
    athlete_count: Optional[int] = None
    photo_count: Optional[int] = None
    map: Optional[StravaMapModel] = None
    trainer: Optional[bool] = None
    commute: Optional[bool] = None
    manual: Optional[bool] = None
    private: Optional[bool] = None
    visibility: Optional[str] = None
    flagged: Optional[bool] = None
    gear_id: Optional[str] = None
    start_latlng: Optional[List[float]] = None
    end_latlng: Optional[List[float]] = None
    average_speed: Optional[float] = None
    max_speed: Optional[float] = None
    average_watts: Optional[float] = None
    max_watts: Optional[float] = None
    weighted_average_watts: Optional[float] = None
    device_watts: Optional[bool] = None
    kilojoules: Optional[float] = None
    has_heartrate: Optional[bool] = None
    average_heartrate: Optional[float] = None
    max_heartrate: Optional[float] = None
    heartrate_opt_out: Optional[bool] = None
    display_hide_heartrate_option: Optional[bool] = None
    elev_high: Optional[float] = None
    elev_low: Optional[float] = None
    upload_id: Optional[int] = None
    upload_id_str: Optional[str] = None
    external_id: Optional[str] = None
    from_accepted_tag: Optional[bool] = None
    pr_count: Optional[int] = None
    total_photo_count: Optional[int] = None
    has_kudoed: Optional[bool] = None
    suffer_score: Optional[int] = None
    average_cadence: Optional[float] = None
    average_temp: Optional[float] = None
    calories: Optional[float] = None
    segment_efforts: Optional[List[SegmentEffortModel]] = None
    splits_metric: Optional[List[Dict[str, Any]]] = None
    laps: Optional[List[LapModel]] = None
    gear: Optional[GearModel] = None
    partner_brand_tag: Optional[str] = None
    photos: Optional[PhotosModel] = None
    highlighted_kudosers: Optional[List[HighlightedKudoserModel]] = None
    hide_from_home: Optional[bool] = None
    device_name: Optional[str] = None
    embed_token: Optional[str] = None
    segment_leaderboard_opt_out: Optional[bool] = None
    leaderboard_opt_out: Optional[bool] = None
    description: Optional[str] = None
    splits_standard: Optional[List[Dict[str, Any]]] = None
    perceived_exertion: Optional[Any] = None
    prefer_perceived_exertion: Optional[Any] = None
    stats_visibility: Optional[List[Dict[str, Any]]] = None
    available_zones: Optional[List[str]] = None
