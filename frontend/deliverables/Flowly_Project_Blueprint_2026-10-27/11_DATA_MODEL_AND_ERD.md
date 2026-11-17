# Flowly Project Blueprint

**Prepared:** 27 October 2026  
**Scope:** Flowly bilingual AI, software and automation website, hosted preview and EC2 distribution.  
**Status key:** Implemented = present in the website or portable distribution; Planned = requires a real provider, legal review, commercial decision, or delivery engagement.

## Data model
```mermaid
erDiagram
  REQUESTS ||--o{ APPOINTMENTS : has
  REQUESTS ||--o{ REQUEST_EVENTS : records
  REQUESTS { string id PK
    string reference UK
    string status
    string details
  }
  APPOINTMENTS { string id PK
    string request_id FK
    string slot
    string status
  }
  REQUEST_EVENTS { string id PK
    string request_id FK
    string event_type
    string status
    string created_at
  }
```

Form details are stored as structured JSON in the request record. Internal notes are restricted to authorized staff and never returned by public request lookup.
