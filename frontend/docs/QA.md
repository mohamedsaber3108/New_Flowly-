# Validation record

Date: 23 October 2026.

## Automated

- Strict TypeScript check.
- Hosted production build and standalone Vite client / Node server builds.
- Catalog integrity: 45 unique services, all original IDs 01–18, 180 bilingual feature pairs, and valid references from all fourteen industry entries.
- Twelve integration checks against the real standalone Node/SQLite adapter: consent, email validation, past-date rejection, required governmental department, cross-origin rejection, durable save/reference, idempotent retry, duplicate-slot conflict, saved-slot availability, relevant guide links, Arabic government routing and health.

## Browser

- Desktop homepage visually reviewed in light English and dark Arabic.
- RTL direction and stored theme/language verified through the rendered document.
- No broken images on the reviewed homepage.
- Catalog search produced filtered results and preserved input focus.
- Actual governmental discovery journey completed with explicitly fictional QA data: audience, goals, description, department, on-premise preference, government recommendations, contact, date/time and consent.
- Hosted-preview D1 saved the request and returned `FLW-20261023-9DE6AC5F`; the confirmation screen correctly said the appointment was provisional. This is local preview test data only; it is not migrated to production.
- Assistant opened bottom-right, accepted an ERP prompt, returned relevant service links and identified guided mode.
- AI ERP and government pages loaded with correct headings and page-specific document titles.
- Mobile reviewed in a 390 px iframe. Arabic dark homepage had an actual content width of 375 px (scrollbar accounted for) and no horizontal overflow. Consultation page also measured 375 px with no horizontal overflow. This is responsive browser-frame QA, not a physical-device test.
- Reduced-motion styles are included.
- Action buttons use #CE4816 with white labels (calculated contrast about 4.60:1). Small orange text uses a deeper shade on light surfaces.

## Limits

No paid AI call was made; provider credentials were not supplied. Bedrock, Dify and compatible API adapters are configured through server-side environment settings, and actual provider operation must be checked after credentials/model access are configured. No email, external calendar or meeting-provider integration is configured. The private preview and standalone EC2 distribution use different databases. This is a marketing/intake website, not a completed ERP or all client-facing platforms described in the source blueprint.

The checks establish the observed behaviors, not a guarantee of zero defects or an independent security audit.

## Customer-readiness extension — 24 October 2026

- Existing page, identity and catalog components were retained. Additions: request tracking, protected team inbox and follow-up, reversible appointment release, CSV export, search metadata and a social sharing card.
- Strict TypeScript, hosted production build and standalone React/Node build passed.
- Standalone integration checks now cover access denial, customer status lookup and mismatched email, private note isolation, confirmed status, cancellation, slot reuse, collision on attempted reactivation, robots and sitemap.
- New tracking page visually checked in desktop English light and Arabic RTL. A shared preview daemon later switched to an unrelated project, so further UI interaction was not counted as a Flowly test; API checks run against an isolated SQLite database.
- Hosted owner authentication requires testing after publication with the real signed-in owner session; the local managed preview does not emulate this identity. It is not claimed to have been browser verified there.
