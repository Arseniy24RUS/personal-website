# GitHub Pages feasibility for automated scientist portfolio

## Decision

GitHub Pages is viable for version 1 if the system is designed as a static-first publication layer:

1. GitHub Actions harvests public/open data on a schedule.
2. Raw snapshots are saved under `data/snapshots/`.
3. Normalized records are saved under `data/processed/`.
4. Uncertain records are written to `data/admin_queue/`.
5. The public site is rebuilt and deployed as static HTML/JS.

GitHub Pages is not viable as a full dynamic CMS by itself. A true browser admin panel with authentication, database mutations, media storage, and one-click moderation should later move to Supabase/Vercel/Render or a similar stack.

## Current eLibrary snapshot

The uploaded eLibrary HTML contains:

- total RINC publications: 58
- total RINC citations: 262
- parsed publication rows: 58
- RINC category count: 58
- core RINC category count: 19
- Scopus category counts: Q1=4, Q2=0, Q3=5, Q4=1
- Web of Science category counts: Q1=0, Q2=4, Q3=0, Q4=2

## Automation classes

### Can be automated well on GitHub Actions

- ORCID public works and profile.
- OpenAlex author and works.
- Crossref metadata by DOI.
- GitHub profile/repositories/stars/forks.
- eLibrary saved/public HTML parsing when the HTML is accessible to the runner.
- Static rendering of publication lists, metrics, projects and media pages.
- Admin queue as JSON/CSV and GitHub Issues/Pull Requests.

### Can be automated partially

- eLibrary live scraping from GitHub Actions: technically possible, but may be blocked or rate-limited. The safe design is `live-if-available + saved-html fallback`.
- Scopus/WoS metrics without API: public profile pages may render metrics in browser, but stable extraction from GitHub Actions is not guaranteed because of JavaScript, cookies, bot protection, institutional routing and layout changes.
- Media discovery: possible via search APIs/RSS; weak without API keys.

### Should not be promised as fully automatic without external services/API

- Authenticated eLibrary/Scopus/WoS harvesting.
- A non-technical admin panel hosted only on GitHub Pages.
- Reliable media monitoring without Google CSE/SerpAPI/NewsAPI/RSS source lists.
- Direct upload and storage of diplomas/photos through the static website.

## Recommended commercial product model

For non-technical scholars, the minimum-entry version should be:

- `profile.yml` with name, identifiers, affiliations and language settings.
- `/admin-lite.html` for local/offline editing of JSON files.
- GitHub Issues or Pull Requests as moderation queue.
- Drag-and-drop assets into `/content/media/`, `/content/diplomas/`, `/content/photos/`.
- DOI/URL/grant-link importers that create JSON drafts.
- Optional upgrade: hosted CMS with Supabase/Vercel for one-click web administration.
