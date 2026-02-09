"""配置 API"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class TouristAppUrlResponse(BaseModel):
    url: str


@router.get("/tourist-app-url", response_model=TouristAppUrlResponse)
async def get_tourist_app_url():
    url = (settings.TOURIST_APP_URL or "").strip()
    return TouristAppUrlResponse(url=url)
