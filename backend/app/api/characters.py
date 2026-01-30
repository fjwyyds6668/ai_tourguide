"""
角色管理 API
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.core.prisma_client import get_prisma

router = APIRouter()

class CharacterCreate(BaseModel):
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    style: Optional[str] = None
    prompt: Optional[str] = None
    voice: Optional[str] = None  # TTS voice name
    live2d_character_name: Optional[str] = None  # Live2D character name, e.g., "Mao", "Chitose"
    live2d_character_group: Optional[str] = "free"  # Live2D character group, default "free"
    is_active: bool = True

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    style: Optional[str] = None
    prompt: Optional[str] = None
    voice: Optional[str] = None  # TTS voice name
    live2d_character_name: Optional[str] = None  # Live2D character name
    live2d_character_group: Optional[str] = None  # Live2D character group
    is_active: Optional[bool] = None

class CharacterResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    avatar_url: Optional[str]
    style: Optional[str]
    prompt: Optional[str]
    voice: Optional[str]  # TTS voice name
    live2d_character_name: Optional[str]  # Live2D character name
    live2d_character_group: Optional[str]  # Live2D character group
    is_active: bool
    created_at: str
    updated_at: Optional[str]

@router.get("/characters", response_model=List[CharacterResponse])
async def get_characters(active_only: bool = True):
    """获取角色列表"""
    try:
        prisma = await get_prisma()
        
        where_clause = {"isActive": True} if active_only else {}
        characters = await prisma.character.find_many(where=where_clause, order={"createdAt": "desc"})
        
        return [
            CharacterResponse(
                id=char.id,
                name=char.name,
                description=char.description,
                avatar_url=char.avatarUrl,
                style=char.style,
                prompt=char.prompt,
                voice=char.voice,
                live2d_character_name=char.live2dCharacterName,
                live2d_character_group=char.live2dCharacterGroup,
                is_active=char.isActive,
                created_at=char.createdAt.isoformat() if char.createdAt else "",
                updated_at=char.updatedAt.isoformat() if char.updatedAt else None
            )
            for char in characters
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/characters/{character_id}", response_model=CharacterResponse)
async def get_character(character_id: int):
    """获取角色详情"""
    try:
        prisma = await get_prisma()
        character = await prisma.character.find_unique(where={"id": character_id})
        
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        return CharacterResponse(
            id=character.id,
            name=character.name,
            description=character.description,
            avatar_url=character.avatarUrl,
            style=character.style,
            prompt=character.prompt,
            voice=character.voice,
            live2d_character_name=character.live2dCharacterName,
            live2d_character_group=character.live2dCharacterGroup,
            is_active=character.isActive,
            created_at=character.createdAt.isoformat() if character.createdAt else "",
            updated_at=character.updatedAt.isoformat() if character.updatedAt else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/characters", response_model=CharacterResponse)
async def create_character(character: CharacterCreate):
    """创建新角色"""
    try:
        prisma = await get_prisma()
        new_character = await prisma.character.create(
            data={
                "name": character.name,
                "description": character.description,
                "avatarUrl": character.avatar_url,
                "style": character.style,
                "prompt": character.prompt,
                "voice": character.voice,
                "live2dCharacterName": character.live2d_character_name,
                "live2dCharacterGroup": character.live2d_character_group,
                "isActive": character.is_active
            }
        )
        
        return CharacterResponse(
            id=new_character.id,
            name=new_character.name,
            description=new_character.description,
            avatar_url=new_character.avatarUrl,
            style=new_character.style,
            prompt=new_character.prompt,
            voice=new_character.voice,
            live2d_character_name=new_character.live2dCharacterName,
            live2d_character_group=new_character.live2dCharacterGroup,
            is_active=new_character.isActive,
            created_at=new_character.createdAt.isoformat() if new_character.createdAt else "",
            updated_at=new_character.updatedAt.isoformat() if new_character.updatedAt else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/characters/{character_id}", response_model=CharacterResponse)
async def update_character(character_id: int, character: CharacterUpdate):
    """更新角色信息"""
    try:
        prisma = await get_prisma()
        
        existing = await prisma.character.find_unique(where={"id": character_id})
        if not existing:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        update_data = {}
        if character.name is not None:
            update_data["name"] = character.name
        if character.description is not None:
            update_data["description"] = character.description
        if character.avatar_url is not None:
            update_data["avatarUrl"] = character.avatar_url
        if character.style is not None:
            update_data["style"] = character.style
        if character.prompt is not None:
            update_data["prompt"] = character.prompt
        if character.voice is not None:
            update_data["voice"] = character.voice
        if character.live2d_character_name is not None:
            update_data["live2dCharacterName"] = character.live2d_character_name
        if character.live2d_character_group is not None:
            update_data["live2dCharacterGroup"] = character.live2d_character_group
        if character.is_active is not None:
            update_data["isActive"] = character.is_active
        
        updated_character = await prisma.character.update(
            where={"id": character_id},
            data=update_data
        )
        
        return CharacterResponse(
            id=updated_character.id,
            name=updated_character.name,
            description=updated_character.description,
            avatar_url=updated_character.avatarUrl,
            style=updated_character.style,
            prompt=updated_character.prompt,
            voice=updated_character.voice,
            live2d_character_name=updated_character.live2dCharacterName,
            live2d_character_group=updated_character.live2dCharacterGroup,
            is_active=updated_character.isActive,
            created_at=updated_character.createdAt.isoformat() if updated_character.createdAt else "",
            updated_at=updated_character.updatedAt.isoformat() if updated_character.updatedAt else None
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/characters/{character_id}")
async def delete_character(character_id: int):
    """删除角色"""
    try:
        prisma = await get_prisma()
        
        existing = await prisma.character.find_unique(where={"id": character_id})
        if not existing:
            raise HTTPException(status_code=404, detail="角色不存在")
        
        await prisma.character.delete(where={"id": character_id})
        
        return {"message": "角色删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

