# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Lifecycle
1. Visitor submits a consented brief.
2. API validates, rate-limits, writes request and `submitted` event.
3. Optional appointment is provisional.
4. Owner updates request status; each status transition writes a non-sensitive event.
5. Visitor can retrieve only their own status using reference plus email.
6. Retention, deletion verification and backup restoration are operating procedures still requiring a named owner and approved schedule.
