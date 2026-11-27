# Upload Flowly to GitHub

This archive is the full Flowly project after the latest updates.

## Included
- React/Vinext website source in `app/`, `components/`, `lib/`, `public/`.
- API and data definitions in `lib/api.ts`. The old Cloudflare/D1 routes, `db/` and `drizzle/` now live in `legacy/` (not deployed).
- Hosted Site configuration in `.openai/hosting.json`.
- EC2 Node/SQLite source in `portable/` and a ready build in `ec2-dist/`.
- Customer-readiness documentation in `docs/`.
- Flowly Blueprint package in `deliverables/`.

## Before pushing
1. Extract the ZIP and create an empty GitHub repository.
2. Keep `.gitignore`; it deliberately excludes dependencies, local database files, secrets, build caches and editor state.
3. Run `pnpm install --frozen-lockfile` and `pnpm build` to validate the hosted build.
4. For EC2, use the files in `ec2-dist/` or rebuild from source using the commands in `docs/EC2_DEPLOYMENT.md`.
5. Never commit `.env`, `ADMIN_TOKEN`, AI provider keys, production database files or backup archives.

## First commit
```bash
git init
git add .
git commit -m "Initial Flowly project"
git branch -M main
git remote add origin <YOUR_GITHUB_REPOSITORY_URL>
git push -u origin main
```
