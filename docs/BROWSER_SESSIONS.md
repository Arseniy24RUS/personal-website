# Browser session operations

The weekly refresh runs on Monday at 06:17 Moscow time. Tuesday–Sunday at the
same time (`17 3 * * 0,2-6` UTC), the workflow only verifies eLibrary/WoS authorization and saves a
fresh encrypted checkpoint. Maintenance does not publish files or advance
publication, citation, or collection success dates. All provider requests use
the existing verified home VPN. GitHub schedules can be delayed or skipped.

## Storage and credentials

Set the repository Secret `BROWSER_SESSION_KEY` to base64 of 32 random bytes.
Keep the existing provider login and VPN Secrets. This architecture uses no PAT,
local worker or always-on browser. Its WoS portability and renewal still require
the live acceptance checks below. Never put the key in a command argument or print it.

Each provider gets an AES-256-GCM artifact named `browser-session-v1-elibrary`
or `browser-session-v1-wos`, retained for 90 days. The authenticated envelope
binds its schema, repository, provider and author ID; each encryption has a new random nonce.
The existing `GITHUB_TOKEN` reads artifacts with `actions: read`; upload-artifact
uses the current Actions run's upload credentials. There is no Secret-writing
token in the workflow.

Restore accepts only this repository's main-branch scheduled/manual runs from
`refresh-data.yml` and its two checked-in legacy wrappers (`test-wos-dom.yml`,
`refresh-media-corpus.yml`). The run conclusion is not an authorization signal:
one provider can checkpoint successfully even when another provider later fails.
Within the recent candidates, the newest confirmed `validated_at` wins. Invalid,
wrong-target and corrupt artifacts are skipped. A failed restore is reported and
collectors can use the normal login fallback.

Artifacts in a public repository are not private storage. Only ciphertext may
be uploaded as a session artifact. Authentication values stay in the restricted
runner runtime or browser memory. Public reports have only fixed status markers
and timestamps. `session-outbox` contains ciphertext and survives VPN cleanup;
plaintext `portfolio-runtime` is removed by the existing cleanup step. Reports
under `session-reports` are separate from scientific data and retained for 7 days.

The first-party cookie allowlist is `SCookieGUID`, `SUserID` for eLibrary and
`WOSSID`, `dotmatics.elementalKey`, `group` for WoS. Analytics and unrelated
origins are excluded. Cloud checkpoints additionally permit state for the
explicit official ORCID/Clarivate authentication origins in `browser_sessions.py`.
Do not broaden this list without observing why an origin is required.

## Bootstrap an authorized session

Use the supported browser's scoped export of cookies and observed authentication
storage. Do not export the whole user's browser profile or unrelated tabs.
Preserve cookie domain/path, expiry, HttpOnly, Secure and SameSite attributes.
The input is standard Playwright storage state: `{"cookies": [...], "origins": [...]}`.
Cookies alone must not be described as a complete authenticated session.

The working WoS tab contains a localStorage entry named `wos_sid`: its value is a
JSON-encoded string, and that decoded string matched the WOSSID cookie during the
20 September inspection. Preserve the original storage value, including its JSON
encoding, under origin `https://www.webofscience.com`. Initial cookie-only seeds
omitted this entry. Do not infer that restoring this entry guarantees server-side
account authorization; the live profile and account checks remain mandatory.

In the current IAB, the supported tab-scoped CDP `Runtime.evaluate` command can
read localStorage. An unsupported `DOMStorage.getDOMStorageItems` command does not
establish that all storage export is unavailable. Read names/counts first; keep
actual values in memory or the restricted temporary directory and encrypt them
before passing them to Actions. Never print the CDP response containing values.
Only the observed authentication entry is needed for this controlled comparison;
do not include search history or analytics. The observed IndexedDB database and
sessionStorage names were analytics/navigation state, with no established auth
requirement. No full browser-profile export is assumed.

See [Playwright authentication](https://playwright.dev/python/docs/auth) for the
storage-state format and the separate handling required by sessionStorage.

In a private temporary directory, with `BROWSER_SESSION_KEY` provided through the
environment, run:

```text
python scripts/browser_sessions.py encrypt-bootstrap --provider elibrary --input PRIVATE/elibrary.json --output PRIVATE/elibrary.enc.json
python scripts/browser_sessions.py encrypt-bootstrap --provider wos --input PRIVATE/wos.json --output PRIVATE/wos.enc.json
python scripts/browser_sessions.py pack-bootstrap --elibrary PRIVATE/elibrary.enc.json --wos PRIVATE/wos.enc.json --output PRIVATE/bootstrap.txt
```

The commands never print cookie values. Pass the contents of `bootstrap.txt` as
the `session_bootstrap` input of the main-branch workflow_dispatch and enable
`maintain_session` for the initial authentication-only check. GitHub dispatch
inputs are not secrets: this input must contain ciphertext only. The CLI limits
it to 60,000 characters (GitHub's combined inputs limit is 65,535). Remove the
temporary plaintext after dispatch. Bootstrap packages expire after one day.

A bootstrap is unconfirmed. Only live account authorization plus the configured
author target allow a collector to write a confirmed artifact. A second separate
maintenance run without any bootstrap proves restoration on a new runner. Then
perform a dry-run collection and compare fresh source metrics/publication scopes.
Only after this proof should successful session reuse be treated as accepted.

## Renewal and failures

An ordinary authenticated visit may renew provider cookies; it is not guaranteed
to do so. Checkpoint metadata reports the observed auth-cookie expiry and whether
it advanced relative to the restored state. Cookie expiries are Unix seconds,
preserved as numbers without 32-bit conversion. The collector never edits expiry
to extend a session. Browser storage and a long-lived cookie do not prove the
server still considers the account authorized.

When the saved state is rejected or absent, the collector may try the ordinary
provider login once. CAPTCHA, MFA, account linking, revoked access and VPN failure
remain explicit failures, retaining the last published data. Repeatedly submitting
credentials or solving/bypassing challenges is outside this workflow. New manual
authorization may be needed, using the same encrypted bootstrap procedure.

Ninety-day artifact retention covers a thirty-day execution outage, unless someone
deletes the run/artifact. It cannot guarantee server authorization through that
outage. For WoS, observe real daily renewal and a run beyond the initial seven-day
cookie boundary before claiming durable renewal. Session-only maintenance reports
must never be used as evidence of freshly collected publication metrics.

## Rotate the encryption key

1. Temporarily save the old key as `BROWSER_SESSION_PREVIOUS_KEY` and replace
   `BROWSER_SESSION_KEY` with a newly generated 32-byte key.
2. Run maintenance. Restore accepts either key; all new checkpoints use the new
   current key. Check that both providers produce confirmed checkpoints.
3. Remove `BROWSER_SESSION_PREVIOUS_KEY`, then run maintenance once more to prove
   restoration without the previous key.

Older ciphertext remains until retention expires. If a key was compromised,
revoke the affected provider sessions as well; removing artifacts alone does not
revoke captured cookies. Normal session rotation is automatic and does not need
weekly encryption-key changes.

## Regression checks

```text
python -m unittest discover -s tests/unit -p test_browser_sessions.py -v
```

Tests cover altered ciphertext, wrong keys/author/provider, allowed origins,
64-bit expiry, bootstrap vs confirmed state, a thirty-day gap, failed trusted
runs, fork/branch rejection, prior-key migration, checkpoint preservation,
archive path rejection, and maintenance isolation from public data.

## Preserving the verified tab

A confirmed checkpoint must take tab-specific sessionStorage from the actual
verified profile page. A later empty tab for the same origin must not overwrite
that state. Other same-origin conflicts fail the checkpoint without replacing the
last confirmed artifact; they are not resolved by picking whichever tab is last.

## Recognizing the current WoS account menu

The authorized Russian interface observed on 20 September uses
`button[data-ta="wos-header-user_name"]` with an accessible label describing the
account menu, not just the user's name. Its visible logout entries are
`Завершить сеанс` and `Завершить сеанс и выйти`. Opening this menu and checking
these entries is authorization evidence; seeing the account button alone is not.
The collector only observes logout entries and never activates them. This fixes
a false-negative authentication check without relaxing challenge detection.
