# Document search — interview brief

## The product

Several companies use this application to search their own documents. Every
user belongs to exactly one company. A search must return only documents
that user is permitted to read — never another company's documents, and
never a document a specific grant has not covered.

## The recent change

**PR 418: cache search results to speed up repeated searches.**

Searching the full document index is expensive, so a teammate added an
in-memory cache in front of it. The change shipped without an access
review. Your job is to review it, decide whether it can ship, investigate
its actual behavior, and respond to a change in conditions the panel will
introduce partway through.

## Required behaviors

- A user can see only documents allowed by their current permissions.
- Identical searches by different companies cannot leak documents across
  companies.
- Removing a user's access takes effect on the next request, including a
  cached request.
- Repeated authorized searches avoid repeating the expensive search
  operation where possible.

Disabling caching entirely is a valid immediate containment decision. It
satisfies the access behaviors above but leaves the last one — avoiding
repeated expensive work — unresolved. The checks will show that cost; you
are not expected to prefer one implementation over another, only to explain
the tradeoff.

## Files

Editable:

- `search.py` — the search entry point described below.
- `cache.py` — the in-memory cache added by PR 418.
- `permissions.py` — company membership and document grants.

Read-only:

- `index.py` — the expensive document index. Every call to
  `expensive_search(query)` increments a module-level counter,
  `index.SEARCH_CALLS`, so the checks can measure how much repeated work a
  cache avoids.
- `fixtures/users.json`, `fixtures/documents.json`, `fixtures/permissions.json`
  — the synthetic data the application reads at run time.

## Contracts you must keep

- `search(user_id, query)` in `search.py` takes an authenticated user id and
  a query string and returns a list of `{"id", "title"}` dictionaries for
  the documents that user may read. The caller never supplies a company id;
  it always comes from the user's own record.
- `permissions.revoke(user_id, document_id)` in `permissions.py` removes one
  user's access to one document. Admin tooling calls this directly; keep its
  name and signature so that tooling keeps working.

Both files can be restructured internally as long as these entry points
keep their name, arguments, and return shape.

## How checks run

Each check runs in a fresh Python interpreter, so nothing in one check —
cached entries, revoked grants — can leak into the next. A check is a
sequence of steps: `search` (run a query as a user) or `revoke` (remove a
grant). The runner reports exactly what your code returned; it does not
decide pass or fail itself.
