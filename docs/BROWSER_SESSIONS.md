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
`WOSSID`, `dotmatics.elementalKey`, `group`, `__cf_bm` for WoS. Analytics and unrelated
origins are excluded. Cloud checkpoints additionally permit state for the
explicit official ORCID/Clarivate authentication origins in `browser_sessions.py`.
Do not broaden this list without observing why an origin is required.

`__cf_bm` was observed on the user's authorized WoS browser session. Its ordinary
first-party value is retained only for `webofscience.com` and
`www.webofscience.com`, with its original domain, path, expiry and browser
attributes. The checkpoint does not manufacture or renew this cookie; an expired
value is passed through unchanged and the browser enforces its expiry. It is not
used to calculate the WoS account-session expiry.
[Cloudflare documents](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies/)
a lifetime of 30 minutes of continuous inactivity, and its
[bot-score documentation](https://developers.cloudflare.com/bots/concepts/bot-score/)
describes smoothing request scores to reduce false positives in ordinary sessions.
Filtering previously omitted this state at checkpoint/restore boundaries; it did
not remove it from the running browser. This observation does not establish the
cause of WoS hCaptcha, guarantee transfer of trust between runners, or provide
week-long continuity. No challenge response or cookie expiry is fabricated.

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

## Native WoS CV export

For a controlled comparison with a new interactive ORCID login, dispatch the
refresh workflow with `wos_auth_mode: fresh_orcid`, `sources: wos` and
`dry_run: true`. This mode is selected before browser creation: it starts an
empty context and performs the ordinary WoS sign-in flow once. It does not
restore saved authentication into that context, delete previous artifacts, or
retry a challenge in another context. A successful checkpoint may compare its
expiry with the previous saved metadata. The default and scheduled mode remains
`restore`.
The report distinguishes the requested mode from a verified login and records
only fixed stage names and boolean evidence of the sign-in steps. A session
restore failing on a profile challenge is not evidence that a fresh ORCID login
was attempted or failed.

WoS continues to use the existing ORCID sign-in credentials. The login loop
tracks a delayed identity-provider popup and its return to the originating
window within the same attempt; a popup does not trigger another submission.
Only the observed official HTTPS login origins can receive interaction.

After verifying the author and checkpointing profile metrics, the collector
uses **Export CV → Export full profile → JSON → Download my profile**. It selects
the full date range and includes accession numbers, authors and citations.
JSON selection hides the PDF-only field checkboxes; collection does not depend
on those controls. The returned document still has to pass the parser's field
and completeness checks. Account verification closes the menu it opened so
the menu backdrop cannot intercept the following export action.
The site creates and polls its own download job. The collector only observes
responses for the job created by its current Download action; it does not replay
private API requests. Neither the full CV nor its encoded contents are published.

The parser accepts only the requested ResearcherID and separates Core `WOS:`
records from other collections. Core completeness requires equality of the total
Core count, selected-period Core count and distinct valid Core identifiers.
Total citation metrics are separate from the date-limited fields; known zero and
unknown values remain distinct. In the observed export the Core list was complete
although the full-profile list omitted an undated document.

A failed export falls back to the rendered list after verifying the account and
author again. An authorization failure or CAPTCHA ends collection while keeping
the metrics and records already checkpointed. The browser UI and cloud execution
must be tested separately: a user completing a challenge locally is not evidence
that an independent Actions runner will avoid another challenge.
Export diagnostics retain only an allowlisted operation name and failure reason,
never an interaction exception, page contents or download address.

The workflow currently has no Clarivate API keys. The existing Researcher API
application was observed pending approval on 21 September 2026. Browser
collection does not wait for that approval; API support remains optional.

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

## Authentication investigation, 20 September 2026

The deployment remains GitHub Actions through the home VPN. The proposed local
Windows worker was declined; do not install one or change the hosting model.

The [hCaptcha FAQ](https://docs.hcaptcha.com/faq) says repeat challenges depend
on confidence, site difficulty and other security factors. A working home-browser
visit does not establish which factor caused an Actions challenge. The workflow
already runs a headed browser through the verified home route. Fingerprint
spoofing, synthetic human behavior and CAPTCHA solvers are not part of this system.

A CAPTCHA response is distinct from a WoS login session. The
[hCaptcha developer guide](https://docs.hcaptcha.com/#siteverify-error-codes-table)
documents single-use responses and expiry. Saving such a response is not a way
to authorize future weekly runs. Passing one challenge does not establish that
another runner will never receive one.

[WoS sign-in guidance](https://webofscience.zendesk.com/hc/en-us/articles/20011617329425-Registering-and-Signing-in-to-the-Web-of-Science)
documents the English `End session` action and stale localStorage tokens.
On explicit WoS expiry, reset WoS state only; retain allowlisted identity-provider
state for ordinary SSO. The [ORCID OAuth guide](https://info.orcid.org/documentation/integration-guide/customizing-the-sign-in-register-screen/)
allows authorization without another password form. Password submission is not
an authentication requirement: the live account and target profile are.

Run 35524641785 observed a visible hCaptcha frame without recognized interactive
controls. This alone cannot distinguish a transient loader from a persistent
challenge. A bounded, observation-only readiness wait may let an automatic check
finish naturally. It must never click, hide or modify the widget, and a persistent
or interactive challenge remains a blocking failure. Collection and checkpointing
still require the normal positive account and author checks afterward.

## Publication rendering, 20 September 2026

Run [35529362324](https://github.com/Arseniy24RUS/personal-website/actions/runs/35529362324)
verified the existing WoS session, collected fresh metrics and saved a confirmed
encrypted session. Publication collection then timed out with
`profile_records_not_ready`. This was a separate failure after successful login.

The same condition was reproduced in an authorized desktop-browser tab: the
selected Core Collection scope reported 13 publications, but all 13 `app-record`
elements had no text and zero height below the viewport. Ordinary scrolling that
brought the list into view caused all 13 cards to render, without another login
or CAPTCHA. The current parser reads all 13 rendered cards correctly. Collection
therefore needs to bring the actual list into view before waiting for its contents;
longer HTML polling alone does not resolve lazy rendering. This action does not
change authentication or challenge handling.

That run proves one successful cloud authentication and metric collection, not
durable renewal. A separate runner must restore its confirmed artifact without a
new browser bootstrap and collect the complete list. Expiry-boundary validation
remains necessary afterward.

Run [35531006362](https://github.com/Arseniy24RUS/personal-website/actions/runs/35531006362)
then restored the confirmed checkpoint without bootstrap, verified authorization,
collected all 13 records and fresh metrics, and saved its own confirmed state.
The production repeat
[35531406985](https://github.com/Arseniy24RUS/personal-website/actions/runs/35531406985)
restored that new state but encountered a visible hCaptcha frame on profile entry.
The frame remained after the ten-second observation budget; recognized checkbox,
challenge controls and text markers were absent. This proves intermittent
interruption despite successful state portability, not reliable avoidance of
CAPTCHA. The published values and last confirmed state were retained.

A single bounded observation of up to 60 seconds at WoS profile entry is a
diagnostic check for slower automatic verification. It must retain the normal
short budget elsewhere, fail on explicit or incompletely observed challenges,
and never interpret loaded metrics behind a remaining frame as success. Safe
numeric observations can distinguish disappearance after ten seconds from a
persistent interruption; further timeout increases without such evidence do not
establish a cause or solve the challenge.

The bounded experiment
[35532934440](https://github.com/Arseniy24RUS/personal-website/actions/runs/35532934440)
restored the same confirmed session, but the visible hCaptcha frame remained
throughout observation. Its document was already `complete`, with one native
button and 15 button roles in the DOM. The former narrow CSS selectors did not
recognize these controls, so absence of their matches was not evidence of an
empty automatic loader. Increasing the entry window did not establish a fix.
Visible native/ARIA buttons in a recognized challenge frame must therefore stop
collection immediately. A read timeout at an already-known pending challenge's
deadline must retain the challenge classification.

Session portability and one complete automatic collection are confirmed;
reliable CAPTCHA-free collection is not. Do not report the repeated interruptions
as success, extend waits indefinitely, or claim that changing the runner OS
reproduces a trusted home PC. Daily maintenance and the post-expiry acceptance
monitor remain enabled, with the last verified data and session preserved.

## Fresh ORCID login, 21 September 2026

Run [35581139661](https://github.com/Arseniy24RUS/personal-website/actions/runs/35581139661)
started with `fresh_orcid` and did not import the restored WoS state. It reached
the ORCID form, submitted the configured credentials once, and observed HTTP 200
with a successful sign-in response. WoS return and the target profile were not
yet confirmed. The next page observation failed after 1.001 seconds, while its
existing total observation budget was ten seconds. No interactive challenge was
observed in that failed scan. This is evidence of accepted ORCID credentials,
not a successful WoS collection or a CAPTCHA diagnosis.

An individual DOM read can time out or lose its execution context during the
normal login redirect. Recognized temporary read failures are therefore observed
again, without browser actions, within the original shared deadline. The one-second
per-read cap and overall budgets remain unchanged. A complete successful scan is
required before login proceeds; explicit CAPTCHA, MFA, unknown errors and closed
pages still stop the attempt. Diagnostics include only fixed error and read-phase
identifiers, never exception text or redirect URLs. A previously observed challenge
remains a challenge if later reads fail until the deadline.

The user's existing ORCID SSO session may skip the password form altogether.
Do not equate that path with a fresh password login without checking which path
was actually used. Independent collection and post-expiry renewal still need
live acceptance.

The repeat [35583482415](https://github.com/Arseniy24RUS/personal-website/actions/runs/35583482415)
again received a successful ORCID sign-in response. It passed the earlier failed
DOM read, then stopped with `unexpected_login_origin`. Its sanitized browser
diagnostic identified `chromewebdata`, Chromium's own navigation-error document,
not a new identity-provider host. Do not add that internal document to permitted
login origins or classify this outcome as CAPTCHA. Record only fixed navigation
error codes, HTTP status and provider category from this attempt's top-level
document requests; these observations must not contain callback URLs, request
headers or response bodies. A network failure does not authorize a new login
attempt or a session checkpoint.
