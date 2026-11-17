# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Backend sequence
- Zod validates form, lookup and AI inputs. **Implemented.**
- Same-origin validation, payload limits and per-IP hashed rate limits. **Implemented.**
- Idempotent submission key, request reference and slot collision handling. **Implemented.**
- Owner-authorized request management and CSV formula injection protection. **Implemented.**
- Request event ledger for submitted and status-changed events. **Implemented in this release.**
- Notification, CRM and calendar adapters. **Planned after provider selection.**
