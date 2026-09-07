import cache
import index
import permissions


def _normalise(query):
    return " ".join(query.lower().split())


def search(user_id, query):
    key = _normalise(query)
    hits = cache.get(key)
    if hits is None:
        hits = index.expensive_search(query)
        cache.put(key, hits)
    return [{"id": d["id"], "title": d["title"]} for d in hits if permissions.can_read(user_id, d["id"])]
