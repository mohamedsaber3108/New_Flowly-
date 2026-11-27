# frontend/legacy

Old Cloudflare/D1 API. Not deployed. Django backend owns the contract (see /README.md).

Moved here, not deleted (owner question OD-32 / Q-F8, default "move, do not delete"):

| Folder or file | What it was |
|---|---|
| `api/` (was `app/api/`) | Next/vinext API routes on Cloudflare (`/api/requests`, `/api/admin/requests`, ...) |
| `db/`, `drizzle/`, `drizzle.config.ts` | D1 schema and migrations for those routes |
| `examples/` | the D1 example from the starter template |

Still in `frontend/` on purpose, because something else uses it:

- `worker/index.ts`: the Cloudflare worker entry named in `frontend/vite.config.ts`.
- `lib/api.ts`: shared by `portable/server.ts` (the portable Node server).
- `app/chatgpt-auth.ts`: used by `app/team/page.tsx`.

`pnpm db:generate` still works: it points at `legacy/drizzle.config.ts`.
