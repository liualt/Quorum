"""In-memory cache for search results.

Added in the recent caching change so repeated searches skip the
expensive index scan.
"""
_entries = {}


def get(key):
    return _entries.get(key)


def put(key, value):
    _entries[key] = value


def clear():
    _entries.clear()
