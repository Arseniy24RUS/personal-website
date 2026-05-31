# eLibrary weekly refresh

The public eLibrary pages may reject requests from standard GitHub Actions IP
ranges. The portfolio harvester therefore supports two no-API, no-login modes:

1. **Recommended:** run the scheduled workflow with a stable proxy or a
   self-hosted runner on a trusted home/VPS IP.
2. **Fallback:** keep the previous normalized JSON or the latest committed HTML
   snapshot when eLibrary temporarily blocks live access.

## Stable proxy option

Add a repository secret named `ELIBRARY_PROXY_URL` with a standard proxy URL,
for example `http://user:password@host:port`. The eLibrary scripts use this
value through Python `urllib.request.ProxyHandler` for both profile metrics and
publication-list requests. If the secret is absent, the workflow uses the normal
runner network.

## Self-hosted runner option

Install a GitHub self-hosted runner on a machine whose IP can open public
eLibrary author pages in a browser. Use a dedicated low-privilege machine/user
and run the weekly workflow normally. No eLibrary username or password is used
or stored by this repository.

## Diagnostics

Each run writes fetch reports to `data/elibrary/*_fetch_report.json`. Reports
include HTTP status, content length, selected source (`live_elibrary`,
`saved_snapshot`, or `previous_normalized_json`) and an HTML fingerprint that
helps distinguish a real author page from an access-block page.
