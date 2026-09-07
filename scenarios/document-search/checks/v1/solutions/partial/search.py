"""Document search entry point used by the API layer.

search(user_id, query) returns the documents the authenticated user may
read, as a list of {"id", "title"} dictionaries.
"""
import cache
import index
import permissions


def _normalise(query):
    return " ".join(query.lower().split())


def search(user_id, query):
    key = (user_id, _normalise(query))
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = []
    for doc in index.expensive_search(query):
        if permissions.can_read(user_id, doc["id"]):
            results.append({"id": doc["id"], "title": doc["title"]})

    cache.put(key, results)
    return results
