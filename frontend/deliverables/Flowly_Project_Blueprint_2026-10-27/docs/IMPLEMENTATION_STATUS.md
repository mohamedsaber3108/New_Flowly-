# Flowly implementation status

## Implemented

- New vector brand mark, wordmark, orange/cream design system and sculptural vector artwork.
- Self-hosted English and Arabic fonts; responsive layouts; English/Arabic with RTL; persistent light/dark preferences; reduced-motion support.
- Full homepage, catalog search and filters; 45 service detail pages; 14 industry entries; dedicated government route; approach, about, engagement models, journal and policy pages.
- All eighteen blueprint services retain an explicit original service ID in `lib/catalog.ts`.
- Five-step guided discovery with audience, goals, requirements, preliminary recommendations and submission.
- Government-specific department, classification, hosting and procurement/project-reference fields.
- Consultation calendar: Cairo timezone, future Sunday–Thursday dates, 90-day window, configurable-by-code offered times; busy-slot conflict protection.
- Persistent requests and provisional appointments; server-side validation, consent, same-origin checks, bounded payloads, request idempotency and hourly rate limits.
- Request reference, downloadable JSON brief and provisional calendar event.
- Bottom-right companion, catalog guidance and AI provider adapters. UI clearly shows guided mode when AI is not configured.
- Hosted preview uses D1. The EC2 distribution uses Node and SQLite with the same core validation and API logic.
- EC2 Docker, Compose, Caddy, systemd, environment template and authenticated owner export endpoint.
- Private team inbox at `/team`: request search, status changes, internal notes and CSV export. The hosted version authorizes the verified Site owner; EC2 requires `ADMIN_TOKEN`.
- Customer request tracking at `/status` using the request reference plus submitted email. It reveals only the stage and provisional appointment, never the brief or internal note.
- Canceling or declining a request releases its provisional consultation slot. Reclaiming a now occupied slot is rejected atomically.
- Search sitemap, robots policy and branded social preview image. The visual site and original service catalog remain in place.

## Connections needed for live business operations

1. Configure a chosen AI provider: Bedrock on EC2 through IAM, an OpenAI-compatible endpoint, or a Dify app.
2. Configure real calendar/meeting-provider and email/CRM integrations if automatic invitations, calendar synchronization, inbox notifications or CRM delivery are required. Current appointments are stored provisional requests, awaiting team confirmation; no automatic confirmation email or meeting link is claimed.
3. Set the real domain, TLS, origin, data directory, support ownership and backup schedule on EC2.
4. Add verified business contact details, real case studies and any approved commercial terms. No such information was invented.
5. Confirm actual service delivery capacity before publishing the 45-service catalog as a binding offer; each service is a scoped implementation capability, not a prebuilt deployed software product.
6. Review the privacy/terms wording for the operating entity, actual retention policy and provider configuration before public launch.

## Boundaries

This deliverable is the company website and lead/consultation intake system. It does not implement all forty-five advertised client systems. For example, an AI ERP service page is not a working ERP product, and a white-label page does not grant third-party resale rights.

No modifications were made to `flowly.usamif.com`. The hosted version is a separate private preview.
