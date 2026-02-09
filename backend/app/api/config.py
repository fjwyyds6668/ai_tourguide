"""公开配置 API（如游客端入口 URL，用于管理端展示二维码）"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter()


class TouristAppUrlResponse(BaseModel):
    url: str


@router.get("/tourist-app-url", response_model=TouristAppUrlResponse)
async def get_tourist_app_url():
    """获取游客端应用地址，用于管理端生成扫码入口二维码。"""
    url = (settings.TOURIST_APP_URL or "").strip()
    return TouristAppUrlResponse(url=url)
