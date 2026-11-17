# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Audit summary
| Area | Existing state | Safe change in this release |
|---|---|---|
| Brand/UI | Established Flowly visual system | Reused existing patterns only |
| Service catalog | 45 services and filters | No removals or rewrites |
| Intake | Discovery, consultation, contact, government data | No field removal; trust routes link into it |
| Request operations | D1/SQLite persistence, tracking, owner console | Added audit event ledger and storage health |
| AI assistant | Provider-neutral guide with fallback | No expansion of authority/actions |
| EC2 package | Vite/Node/SQLite/Caddy/systemd artifacts | Rebuilt against release changes |

## Safe next changes
Add email/calendar/CRM only through adapters with secrets server-side; add roles before granting multiple staff access; show the audit timeline in the team console once multi-operator workflows are confirmed.
