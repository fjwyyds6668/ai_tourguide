from pymilvus import connections, Collection

COLLECTION_NAME = "tour_knowledge"

connections.connect(alias="default", host="localhost", port="30002")
collection = Collection(COLLECTION_NAME)
collection.load()
collection.delete(expr="text_id like '%'")
collection.flush()