"""
批量导入数据到 Neo4j（图数据库）与 Milvus（向量数据库）。

当前支持：
- 从 PostgreSQL 的 attractions 表导入（通过 Prisma）

用法（在 backend 目录下执行）：
  python import_graphrag_data.py --source attractions --collection tour_knowledge --build-graph --build-attraction-graph
"""

import argparse
import asyncio
from typing import List, Dict, Any

from app.core.prisma_client import get_prisma, disconnect_prisma
from app.core.milvus_client import milvus_client
from app.services.rag_service import rag_service
from app.services.graph_builder import graph_builder
from app.utils.attraction_utils import attraction_to_text


async def upload_texts_to_graphrag(items: List[Dict[str, Any]], collection_name: str, build_graph: bool):
    """
    items: [{"text_id": "...", "text": "..."}]
    """
    collection = milvus_client.create_collection_if_not_exists(collection_name, dimension=384)
    texts = [it["text"] for it in items]
    embeddings = [rag_service.generate_embedding(t) for t in texts]

    entities = [
        [it["text_id"] for it in items],
        embeddings,
    ]
    collection.insert(entities)
    collection.flush()

    total_entities = 0
    if build_graph:
        for it in items:
            extracted = rag_service.extract_entities(it["text"])
            total_entities += len(extracted)
            await graph_builder.extract_and_store_entities(it["text"], it["text_id"], extracted)

    return {"uploaded": len(items), "total_entities": total_entities}


async def import_attractions(collection_name: str, build_graph: bool, build_attraction_graph: bool, limit: int | None):
    prisma = await get_prisma()
    attractions = await prisma.attraction.find_many(order={"id": "asc"}, take=limit)

    att_dicts: List[Dict[str, Any]] = []
    for a in attractions:
        att_dicts.append(
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "location": a.location,
                "latitude": a.latitude,
                "longitude": a.longitude,
                "category": a.category,
            }
        )

    if build_attraction_graph:
        await graph_builder.build_attraction_graph(att_dicts)

    items = []
    for att in att_dicts:
        text = attraction_to_text(att)
        if not text:
            continue
        items.append({"text_id": f"attraction_{att['id']}", "text": text})

    result = await upload_texts_to_graphrag(items, collection_name, build_graph)
    result.update({"attractions": len(items), "build_attraction_graph": build_attraction_graph})
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["attractions"], required=True)
    parser.add_argument("--collection", default="tour_knowledge")
    parser.add_argument("--build-graph", action="store_true", help="写入 Neo4j Text/Entity/MENTIONS")
    parser.add_argument("--build-attraction-graph", action="store_true", help="写入 Neo4j Attraction/NEARBY")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    try:
        if args.source == "attractions":
            res = await import_attractions(
                collection_name=args.collection,
                build_graph=args.build_graph,
                build_attraction_graph=args.build_attraction_graph,
                limit=args.limit,
            )
            print(res)
    finally:
        await disconnect_prisma()


if __name__ == "__main__":
    asyncio.run(main())


