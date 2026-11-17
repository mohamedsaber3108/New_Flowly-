# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Controls implemented
- Origin checks on mutable endpoints.
- Input schemas, bounded payloads and hashed rate limiting.
- Idempotency key for request submissions.
- Protected admin API and page.
- No-store API responses and content type hardening.
- Security, privacy and terms pages with no unsupported certification claims.

## Required public-launch gates
Legal review, real security contact channel, production secrets, backup test, owner assignment, penetration review proportional to risk and approved incident process.
