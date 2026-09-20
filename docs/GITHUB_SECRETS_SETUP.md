# GitHub Actions secrets

Configure repository secrets in **Settings → Secrets and variables → Actions**:

| Secret | Purpose |
| --- | --- |
| `ELIBRARY_OPENVPN_CONFIG_B64` | Existing home OpenVPN configuration |
| `ELIBRARY_USERNAME`, `ELIBRARY_PASSWORD` | Fresh eLibrary sign-in each run |
| `WOS_ORCID_USERNAME`, `WOS_ORCID_PASSWORD` | WoS sign-in through ORCID |
| `SCOPUS_API_KEY` | Elsevier Scopus API key |
| `SCOPUS_INST_TOKEN` | Optional institutional entitlement issued by Elsevier |

The workflow no longer reads legacy cookie or storage-state secrets. A password
change only requires updating its secret; browser sessions are created anew.

Run **Actions → Refresh scientist portfolio data** with `dry_run=true` to verify
credentials and collection without publishing. Inspect the source-health summary
and sanitized diagnostics; a saved snapshot is not successful authentication.

Never commit credentials into Python, YAML, documentation, browser JavaScript or
public JSON. GitHub Pages receives only the validated public data snapshots.
See [refresh operations](REFRESH_OPERATIONS.md) for failure states and deployment.
