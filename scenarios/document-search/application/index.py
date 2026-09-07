"""Expensive document index. Not editable during the interview.

Every call to expensive_search is counted so the checks can measure how
much repeated work a cache avoids.
"""
import json
import os
import re

FIXTURE_DIR = os.environ.get(
    "QUORUM_FIXTURE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"),
)

SEARCH_CALLS = 0


def _load_documents():
    with open(os.path.join(FIXTURE_DIR, "documents.json"), encoding="utf-8") as fh:
        return json.load(fh)["documents"]


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def expensive_search(query):
    """Return every document whose title or body contains all query words."""
    global SEARCH_CALLS
    SEARCH_CALLS += 1
    wanted = _tokens(query)
    hits = []
    for doc in _load_documents():
        haystack = _tokens(doc["title"] + " " + doc["body"])
        if wanted and wanted <= haystack:
            hits.append({"id": doc["id"], "title": doc["title"], "company_id": doc["company_id"]})
    return hits
