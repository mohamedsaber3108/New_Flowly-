# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## EC2 deployment
1. Provision Node 22+ host, private application port and HTTPS reverse proxy.
2. Copy `ec2-dist/` and set `PUBLIC_ORIGIN`, `DATA_DIR`, `ADMIN_TOKEN`; configure optional AI provider secrets only server-side.
3. Use systemd or Docker Compose from the package.
4. Back up SQLite directory safely (WAL-aware) and test a restore.
5. Probe `/api/health`; it now checks storage as well as app response.
6. Roll back by restoring the previous version and verifying health.
