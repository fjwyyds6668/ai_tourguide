"""
清空 Milvus 中指定集合的全部向量数据。

默认使用项目统一的配置（settings + RAG_COLLECTION_NAME），避免与主服务不一致。
"""

import argparse

from pymilvus import connections, Collection

from app.core.config import settings
from app.services.rag_settings import RAG_COLLECTION_NAME


def main():
    parser = argparse.ArgumentParser(description="清空 Milvus 向量集合中的所有向量")
    parser.add_argument(
        "--collection",
        default=RAG_COLLECTION_NAME,
        help=f"Milvus 集合名（默认：{RAG_COLLECTION_NAME}）",
    )
    args = parser.parse_args()

    host = settings.MILVUS_HOST
    port = settings.MILVUS_PORT

    connections.connect(alias="default", host=host, port=port)
    collection = Collection(args.collection)
    collection.load()
    collection.delete(expr="text_id like '%'")
    collection.flush()


if __name__ == "__main__":
    main()