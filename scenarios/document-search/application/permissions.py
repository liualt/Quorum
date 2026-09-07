"""Company membership and document permissions.

Data comes from the fixture files. The caller never supplies a company
identifier; it is derived from the authenticated user.
"""
import json
import os

import index

_users = None
_grants = None


def _load():
    global _users, _grants
    if _users is None:
        with open(os.path.join(index.FIXTURE_DIR, "users.json"), encoding="utf-8") as fh:
            _users = {u["id"]: u for u in json.load(fh)["users"]}
        with open(os.path.join(index.FIXTURE_DIR, "permissions.json"), encoding="utf-8") as fh:
            _grants = {(g["user_id"], g["document_id"]) for g in json.load(fh)["grants"]}


def company_of(user_id):
    _load()
    return _users[user_id]["company_id"]


def can_read(user_id, document_id):
    _load()
    return (user_id, document_id) in _grants


def revoke(user_id, document_id):
    """Remove a user's access to one document. Called by admin tooling."""
    _load()
    _grants.discard((user_id, document_id))
