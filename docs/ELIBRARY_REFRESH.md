# eLibrary weekly refresh

The production entry point is `scripts/harvest_elibrary_browser.py`, invoked by
the common refresh workflow through the existing home OpenVPN connection.
It signs in normally using `ELIBRARY_USERNAME` and `ELIBRARY_PASSWORD` Actions
secrets, verifies authentication and the configured AuthorID, and collects
profile metrics, every publication-list page and article details in one browser
session. Saved cookie strings are not injected into this session.

Metrics and publication lists are fetched each run. Successfully read article
metadata is reused for 30 days for recent works and 90 days for older works;
missing optional fields such as ISBN do not trigger endless repeat requests.
New and failed article pages remain eligible for collection.

The dedicated collector account cannot fall back to direct IPv4 or IPv6 access
if the tunnel drops. Browser profiles and credentials live in private temporary
runner storage and are removed after collection.

`data/elibrary/browser_fetch_report.json` distinguishes a complete fresh login
and collection from retained snapshots. CAPTCHA, MFA, an expired session,
changed HTML and network failure have explicit reasons. A failure retains
published records and the last successful metrics instead of replacing them
with an empty list or zero.

Use the common workflow with `dry_run=true` and `sources=elibrary` for diagnosis.
The older HTTP scripts remain historical utilities; the scheduled workflow does
not use them, a standalone proxy, or a self-hosted runner.

See [refresh operations](REFRESH_OPERATIONS.md) for the schedule, full secret
list, diagnostics and publication checks.
