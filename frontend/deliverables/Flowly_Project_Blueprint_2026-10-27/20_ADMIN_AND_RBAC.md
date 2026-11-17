# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Access model
The public can submit and track only their own request with reference plus email. Team request management is owner-only in hosted preview. EC2 uses a long administrator token, to be stored in a secret manager or protected environment file. Replace single-owner access with audited role-based identity before multiple operators receive access.
