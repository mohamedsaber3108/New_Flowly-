# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Required environment
`PUBLIC_ORIGIN`, `DATA_DIR`, `ADMIN_TOKEN`; optional `AI_PROVIDER`, `AI_API_URL`, `AI_API_KEY`, `AI_MODEL`, `DIFY_API_URL`, `DIFY_API_KEY`, `AWS_REGION`, `BEDROCK_MODEL_ID`.

Store production values outside git. Rotate credentials, alert on health failures, monitor disk/SQLite integrity, and test encrypted backups plus restoration.
