# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## First response runbook
1. Confirm incident scope and preserve logs.
2. If customer data or availability is affected, pause unsafe automation and notify the named incident owner.
3. Use `/api/health` and database checks to identify app versus storage failure.
4. Restore only from a tested backup; record decision, time and owner.
5. Document customer communication and corrective actions.

This is a starter runbook; fill named contacts and notification timelines before public launch.
