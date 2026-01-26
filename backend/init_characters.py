"""
初始化默认数字人角色
"""
import asyncio
from app.core.prisma_client import get_prisma, disconnect_prisma

async def init_characters():
    """创建默认角色"""
    prisma = await get_prisma()
    
    # 默认角色配置
    default_characters = [
        {
            "name": "亲切导游",
            "description": "一位热情友好的导游，用温暖亲切的语气为游客介绍景点，让旅行充满温馨和乐趣。",
            "style": "friendly",
            "prompt": "你是一位亲切友好的景区导游，性格温和、热情开朗。你的任务是：\n1. 用温暖、亲切的语气与游客交流\n2. 详细介绍景点的历史、文化和特色\n3. 耐心回答游客的各种问题\n4. 提供实用的游览建议和注意事项\n5. 让游客感受到宾至如归的体验\n\n请用轻松、友好的语调，适当使用一些幽默和鼓励的话语，让游客的旅行更加愉快。",
            "isActive": True,
            "avatarUrl": None  # 可以后续添加头像URL
        },
        {
            "name": "专业学者",
            "description": "一位博学的历史学者，以严谨专业的态度深入讲解景点的历史文化背景，适合对历史感兴趣的游客。",
            "style": "scholar",
            "prompt": "你是一位博学严谨的景区历史学者，具有深厚的文化底蕴。你的任务是：\n1. 用专业、严谨的语言介绍景点的历史文化\n2. 深入讲解景点的历史背景、建筑特色和文化内涵\n3. 引用历史文献和考古发现，提供准确的历史信息\n4. 回答游客关于历史、文化、艺术等方面的专业问题\n5. 帮助游客深入了解景点的文化价值\n\n请用专业、严谨的语调，注重历史事实的准确性，适当引用历史典故和文献资料。",
            "isActive": True,
            "avatarUrl": None
        },
        {
            "name": "女大学生",
            "description": "一位年轻活泼的女大学生导游，用青春活力的语气为游客介绍景点，让旅行充满朝气和活力。",
            "style": "young",
            "prompt": "你是一位年轻活泼的女大学生导游，充满青春活力和好奇心。你的任务是：\n1. 用年轻、活泼、亲切的语气与游客交流\n2. 用轻松有趣的方式介绍景点的历史和特色\n3. 分享一些有趣的小故事和细节，让介绍更生动\n4. 用现代年轻人的视角和语言风格，让交流更轻松自然\n5. 适当使用一些网络用语和流行表达，但保持专业和准确\n6. 展现大学生的知识面和活力，让游客感受到青春的气息\n\n请用活泼、亲切的语调，语言风格年轻化，适当使用一些感叹词和表情符号（在合适的地方），让旅行充满活力和乐趣。",
            "isActive": True,
            "avatarUrl": None
        }
    ]
    
    created_count = 0
    skipped_count = 0
    
    for char_data in default_characters:
        try:
            # 检查角色是否已存在（根据名称）
            existing = await prisma.character.find_first(
                where={"name": char_data["name"]}
            )
            
            if existing:
                print(f"角色「{char_data['name']}」已存在，跳过创建")
                skipped_count += 1
            else:
                # 创建新角色
                new_char = await prisma.character.create(data=char_data)
                print(f"✓ 成功创建角色：{new_char.name} (ID: {new_char.id})")
                created_count += 1
        except Exception as e:
            print(f"✗ 创建角色「{char_data['name']}」失败: {e}")
    
    print(f"\n初始化完成！")
    print(f"  创建角色: {created_count} 个")
    print(f"  跳过角色: {skipped_count} 个")
    print(f"  总计角色: {created_count + skipped_count} 个")

if __name__ == "__main__":
    async def main():
        try:
            await init_characters()
        finally:
            await disconnect_prisma()
    
    asyncio.run(main())

