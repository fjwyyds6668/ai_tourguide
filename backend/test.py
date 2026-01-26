"""
简单的大模型连通性测试脚本

用法（在虚拟环境中，在 backend 目录下运行）：

    (ai_tourguide) PS E:\毕业设计\项目代码\ai_tourguide\backend> python test.py

会使用 .env 中的 OPENAI_API_KEY / OPENAI_API_BASE / OPENAI_MODEL
向硅基流动（OpenAI 兼容接口）发起一次最简单的对话请求，
成功则打印模型回复，失败会打印具体错误信息。
"""

from app.core.config import settings


def main() -> None:
    try:
        import openai
    except ImportError:
        print("请先在当前环境安装 openai 库，例如：pip install openai")
        return

    # 构造客户端参数（与 rag_service 中保持一致）
    client_kwargs = {"api_key": settings.OPENAI_API_KEY}
    if settings.OPENAI_API_BASE:
        client_kwargs["base_url"] = settings.OPENAI_API_BASE

    print("使用配置：")
    print(f"  OPENAI_API_BASE = {settings.OPENAI_API_BASE!r}")
    print(f"  OPENAI_MODEL    = {settings.OPENAI_MODEL!r}")

    try:
        client = openai.OpenAI(**client_kwargs)

        # 与 test_default_api.py / Postman 示例保持一致：system + user 两条消息
        messages = [
            {
                "role": "system",
                "content": "你是一个有用的助手",
            },
            {
                "role": "user",
                "content": "你好，请介绍一下你自己",
            },
        ]

        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        print("\n调用成功，模型回复：")
        print(resp.choices[0].message.content)
    except Exception as e:
        print("\n调用失败，错误信息：")
        print(repr(e))


if __name__ == "__main__":
    main()


