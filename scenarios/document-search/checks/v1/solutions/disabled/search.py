"""Document search entry point used by the API layer.

search(user_id, query) returns the documents the authenticated user may
read, as a list of {"id", "title"} dictionaries.

Caching disabled: every request re-scans the index, so results can never
go stale, at the cost of the avoided-work behavior.
"""
import index
import permissions


def search(user_id, query):
    results = []
    for doc in index.expensive_search(query):
        if permissions.can_read(user_id, doc["id"]):
            results.append({"id": doc["id"], "title": doc["title"]})
    return results
