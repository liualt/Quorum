# Quorum web

The candidate and reviewer front end: the consent page, the interview workspace
and the assessment report. Next.js 16 (App Router, Turbopack) with Tailwind 4.

## Running it

The app is a front end only — it needs the FastAPI backend in `../server`
running, or every page past `/` will fail. Start that first:

```bash
cd ../server
LLM_PROVIDER=scripted EXECUTOR=local SESSION_SECRET=dev \
DATABASE_PATH=./data/dev.db SNAPSHOT_DIR=./data/dev-snapshots \
uv run uvicorn app.main:create_app --factory --port 8000
```

Then, in this directory:

```bash
npm install
cp .env.local.example .env.local   # only if the backend is not on :8000
npm run dev                        # http://localhost:3000
```

`BACKEND_URL` (default `http://localhost:8000`) is the only environment
variable. `next.config.ts` rewrites `/api/*` and `/llm/*` to it, so the browser
only ever talks to the Next.js origin — that keeps the session cookie
first-party and satisfies the backend's same-origin check on mutations. Point a
deployment at a different backend by setting `BACKEND_URL`; nothing else changes.

## Checks

```bash
npm run lint        # ESLint (next/core-web-vitals + typescript)
npx tsc --noEmit    # types; run `npx next typegen` first on a fresh checkout
npm run build       # production build, which runs typegen and tsc itself
```

## Layout

| Path | What lives there |
| --- | --- |
| `app/` | Routes. Pages are server components; `"use client"` sits on leaves. |
| `app/globals.css` | The design tokens, and the measured contrast table behind them. |
| `components/ui/` | Shared primitives — `Button`, `Chip`, `Panel`, `AIBadge`, … |
| `lib/types.ts` | Wire types mirroring the backend's views by name. |
| `lib/api.ts` | The only module that calls `fetch`. One function per route. |
| `lib/events.ts` | `useSessionEvents` — the SSE subscription. |

Two conventions worth knowing before editing:

- **Colour comes from tokens, never a literal.** `app/globals.css` records the
  measured contrast ratio for every pairing; `--color-border` is decorative and
  `--color-border-strong` is for control boundaries, because only the latter
  clears 3:1.
- **`AIBadge` is the single component that renders the "AI" label.** Disclosure
  is a product commitment, so it looks and reads the same everywhere.

Design rules live in `../design-system/quorum/MASTER.md`.
