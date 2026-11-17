# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Public API
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | App and storage readiness |
| `/api/availability?date=` | GET | Consultation slot availability |
| `/api/requests` | POST | Submit request or consultation |
| `/api/request-status` | POST | Status lookup by reference + email |
| `/api/assistant` | GET/POST | AI or deterministic service guidance |

## Owner API
`/api/admin/requests` lists requests; `/api/admin/requests/:reference` updates status. Hosted access is owner-account gated; EC2 requires a long random `ADMIN_TOKEN`.
