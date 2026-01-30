"""
景点相关工具：向量/图谱文本拼接等
"""
from typing import Dict, Any


def attraction_to_text(attraction: Dict[str, Any]) -> str:
    """将景点记录拼接为用于向量/图谱的文本。"""
    parts = []
    name = attraction.get("name")
    if name:
        parts.append(f"景点：{name}")
    category = attraction.get("category")
    if category:
        parts.append(f"类别：{category}")
    location = attraction.get("location")
    if location:
        parts.append(f"位置：{location}")
    desc = attraction.get("description")
    if desc:
        parts.append(f"介绍：{desc}")
    lat = attraction.get("latitude")
    lng = attraction.get("longitude")
    if lat is not None and lng is not None:
        parts.append(f"坐标：({lat}, {lng})")
    return "\n".join(parts).strip()
