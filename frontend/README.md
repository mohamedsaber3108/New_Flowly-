# Flowly — Intelligence in motion

A bilingual React company website with a new orange/cream identity, 45 connected service offerings, government intake, guided discovery and consultation requests.

## Start here

- `docs/EC2_DEPLOYMENT.md`: standalone EC2 deployment, AI adapters and operating setup (Arabic).
- `docs/IMPLEMENTATION_STATUS.md`: implemented features and connections that remain configurable.
- `docs/RESEARCH_20_COMPANIES.md`: official-source benchmark of twenty companies and service-design decisions.
- `docs/SOURCE_COVERAGE.md`: mapping of the supplied blueprint and the expanded catalog.
- `brand/Flowly-Brand-Identity.html`: visual brand guide; open locally after extracting the complete package.
- `brand/flowly-wordmark-ink.svg`, `flowly-wordmark-reversed.svg`, `flowly-symbol.svg`: editable vector assets; lettering converted to paths.
- `ec2-dist/`: built React + Node distribution (included in the deliverable package, not the hosted repository).

## Architecture

The shared React components live in `components/`; service data and translations in `lib/catalog.ts`. `lib/api.ts` contains provider-neutral validation and API logic. The hosted preview uses Vinext and D1. The portable entrypoints under `portable/` build the same frontend through Vite and run the same API core with Node and SQLite on EC2.

Requests are durable records. Consultation times remain provisional until confirmed by the team. The assistant defaults to transparent catalog guidance; real AI requires an explicitly configured provider. No external calendar, meeting link, email, payment or CRM delivery is simulated.

## Validation

TypeScript check, production builds for both adapters, twelve API integration checks, browser testing of Arabic/RTL, light/dark, discovery, governmental fields, calendar, saved requests, assistant guidance and catalog search. The mobile layout was checked inside a 390 px browser frame. See `docs/QA.md` for evidence and limits.

## Fonts and third-party software

Fonts are self-hosted. Their notices are in `public/fonts/LICENSES/`. Framework dependencies retain their own licenses. Technology names in the service catalog identify possible building blocks, not partnership claims or bundled implementation licenses.
