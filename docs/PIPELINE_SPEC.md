# Static-first pipeline specification

## Inputs

`profile.yml`:

- full_name
- display_name_ru / display_name_en
- identifiers:
  - elibrary_authorid
  - elibrary_spin
  - orcid
  - scopus_author_id
  - wos_researcher_id
  - github_username
  - google_scholar_id
- affiliations
- public contacts

## Scheduled GitHub Actions

`refresh-data.yml` should run daily or weekly and perform:

1. `harvest_orcid.py`
2. `harvest_openalex.py`
3. `harvest_crossref.py`
4. `harvest_github.py`
5. `harvest_elibrary_public.py`
6. `harvest_scopus.py`
7. `normalize_publications.py`
8. `dedupe_publications.py`
9. `build_admin_queue.py`
10. `build_static_site`
11. `deploy_pages`

## Manual one-click imports

Because static GitHub Pages cannot accept uploads directly, each import should be implemented as a local helper script or GitHub Action `workflow_dispatch` input:

- DOI import: `workflow_dispatch` input `doi`
- URL import: `workflow_dispatch` input `url`
- RSF grant import: `workflow_dispatch` input `grant_url`
- eLibrary snapshot import: commit saved HTML to `data/snapshots/elibrary/`
- Diploma/photo import: add file to repository via GitHub web UI; metadata generated automatically

## Admin queue

The queue must be stored as JSON/CSV under `data/admin_queue/` and optionally mirrored into GitHub Issues.

Queue item fields:

- id
- entity_type: publication | media | project | grant | diploma | photo | video
- action: create | update | merge | reject_candidate
- confidence
- reasons
- candidate_record
- matched_existing_record_ids
- source_provenance
- suggested_ru
- suggested_en
