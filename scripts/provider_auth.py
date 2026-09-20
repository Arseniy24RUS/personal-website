"""Normal interactive website login using a fresh Playwright browser context.

Secrets are filled only into the official provider form. No session, HTML,
request URL, exception text or screenshot is written to public diagnostics.
Verification challenges are reported, never solved or bypassed.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse


class AuthFailure(RuntimeError):
    def __init__(self, reason, authentication_evidence=None, verification_evidence=None):
        self.reason = reason
        self.authentication_evidence = authentication_evidence
        self.verification_evidence = verification_evidence
        super().__init__(reason)


def browser_initialization_diagnostics(exc):
    """Classify launch logs privately; publish only fixed allowlisted markers."""
    message = str(exc).lower()
    patterns = {
        'display_unavailable': ('missing x server', 'cannot open display', 'failed to open display', 'unable to open x display'),
        'crashpad_initialization_failed': ('crashpad', 'crash_report_database'),
        'filesystem_permission_denied': ('permission denied', 'eacces', 'access is denied'),
        'browser_executable_missing': ("executable doesn't exist", 'executable not found', 'please run the following command to download new browsers'),
        'browser_library_missing': ('error while loading shared libraries', 'host system is missing dependencies'),
        'browser_sandbox_failed': ('no usable sandbox', 'failed to move to new namespace', 'running as root without --no-sandbox'),
        'browser_process_crashed': ('signal=sigtrap', 'signal=sigsegv', 'trace/breakpoint trap', 'segmentation fault'),
        'browser_process_closed': ('target page, context or browser has been closed', 'target closed'),
        'storage_full': ('no space left on device',),
    }
    signals = [label for label, needles in patterns.items() if any(needle in message for needle in needles)]
    if isinstance(exc, PermissionError) and 'filesystem_permission_denied' not in signals:
        signals.append('filesystem_permission_denied')
    if isinstance(exc, ModuleNotFoundError):
        signals.append('python_dependency_missing')
    priorities = ['display_unavailable', 'filesystem_permission_denied', 'crashpad_initialization_failed', 'browser_executable_missing', 'browser_library_missing', 'browser_sandbox_failed', 'storage_full', 'python_dependency_missing', 'browser_process_crashed', 'browser_process_closed']
    reason = next((label for label in priorities if label in signals), 'browser_initialization_failed')

    def accessible(key, mode):
        path = os.environ.get(key)
        return bool(path and Path(path).is_dir() and os.access(path, mode))

    return {
        'reason': reason,
        'signals': signals,
        'error_type': type(exc).__name__ if type(exc).__name__ in {'TargetClosedError', 'Error', 'TimeoutError', 'PermissionError', 'FileNotFoundError', 'ModuleNotFoundError', 'OSError'} else 'OtherError',
        'environment': {
            'display_configured': bool(os.environ.get('DISPLAY')),
            'home_writable': accessible('HOME', os.W_OK | os.X_OK),
            'runtime_writable': accessible('RUNNER_TEMP', os.W_OK | os.X_OK),
            'xdg_config_writable': accessible('XDG_CONFIG_HOME', os.W_OK | os.X_OK),
            'xdg_cache_writable': accessible('XDG_CACHE_HOME', os.W_OK | os.X_OK),
            'browser_store_readable': accessible('PLAYWRIGHT_BROWSERS_PATH', os.R_OK | os.X_OK),
        },
    }


def safe_browser_diagnostics(context):
    """Allowlist visible form structure, never input values, body or URL queries."""
    output = []
    secrets = [os.environ.get(key, '') for key in ('ELIBRARY_USERNAME', 'ELIBRARY_PASSWORD', 'WOS_ORCID_USERNAME', 'WOS_ORCID_PASSWORD')]

    def clean(value):
        text = str(value or '')[:120]
        for secret in secrets:
            if secret:
                text = text.replace(secret, '[REDACTED]')
        return re.sub(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', '[REDACTED]', text, flags=re.I)

    for page in context.pages[-3:]:
        try:
            address = urlparse(page.url)
            controls = page.eval_on_selector_all('input,button,a,[role="button"]', """els => els.filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)).slice(0,60).map(el => ({tag:el.tagName.toLowerCase(),type:el.getAttribute('type')||'',name:el.getAttribute('name')||'',id:el.id||'',label:el.tagName==='INPUT' ? (el.getAttribute('aria-label')||el.getAttribute('placeholder')||'') : (el.innerText||el.getAttribute('aria-label')||el.title||'').trim().slice(0,120)}))""")
            output.append({'host': clean(address.hostname), 'path': clean(address.path), 'controls': [{key: clean(value) for key, value in control.items()} for control in controls]})
        except Exception:
            continue
    return output


def diagnostic_login(function):
    def wrapped(context, *args, **kwargs):
        try:
            return function(context, *args, **kwargs)
        except Exception as exc:
            failure = exc if isinstance(exc, AuthFailure) else AuthFailure(type(exc).__name__)
            failure.diagnostics = safe_browser_diagnostics(context)
            raise failure from None
    return wrapped


def page_text(page, *, timeout=10000):
    return page.locator('body').inner_text(timeout=timeout)


def in_visible_viewport(locator, *, timeout=None):
    """Playwright is_visible also accepts offscreen and transparent elements."""
    return locator.evaluate("""el => {
        const box = el.getBoundingClientRect();
        let left = Math.max(0, box.left), top = Math.max(0, box.top);
        let right = Math.min(innerWidth, box.right), bottom = Math.min(innerHeight, box.bottom);
        for (let node = el; node; node = node.parentElement) {
            const style = getComputedStyle(node);
            if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0) return false;
            if (node !== el) {
                const clip = node.getBoundingClientRect();
                if (/hidden|clip|scroll|auto/.test(style.overflowX)) {
                    left = Math.max(left, clip.left); right = Math.min(right, clip.right);
                }
                if (/hidden|clip|scroll|auto/.test(style.overflowY)) {
                    top = Math.max(top, clip.top); bottom = Math.min(bottom, clip.bottom);
                }
            }
        }
        return right > left && bottom > top;
    }""", timeout=timeout)


HUMAN_MARKERS = {
    'turing_test_ru': 'тест тьюринга',
    'verify_you_are_human': 'verify you are human',
    'verify_that_you_are_human': 'verify that you are human',
    'unusual_activity': 'unusual activity',
    'challenge_expired': 'challenge has expired',
    'not_robot_ru': 'проверка, что вы не робот',
}

# A known hCaptcha frame may briefly display automatic verification before
# disappearing. This is only an observation budget, never challenge interaction.
CHALLENGE_SETTLE_SECONDS = 10.0
CHALLENGE_POLL_SECONDS = 0.25


class _ChallengeObservationTimeout(RuntimeError):
    pass


def _observation_timeout(deadline):
    """Bound locator auto-waiting and check the shared observation deadline."""
    remaining = 1.0 if deadline is None else deadline - time.monotonic()
    if remaining <= 0:
        raise _ChallengeObservationTimeout()
    return min(1000.0, remaining * 1000)


def human_marker_ids(text, url=''):
    markers = [key for key, value in HUMAN_MARKERS.items() if value in str(text).lower()]
    if 'page_captcha' in url:
        markers.append('page_captcha_url')
    return markers


def challenge_frame_evidence(locator, *, deadline=None):
    """Read geometry and fixed challenge signals; never emit frame text/values."""
    result = {'frame_dom_observed': False, 'checkbox_present': None, 'checkbox_visible': None, 'checkbox_checked': None, 'active_challenge_controls': None}
    try:
        # Only known static provider paths are retained. In particular, do not
        # export src query parameters, fragments, arbitrary paths or frame names.
        src = locator.get_attribute('src', timeout=_observation_timeout(deadline)) or ''
        address = urlparse(src)
        host = (address.hostname or '').lower()
        allowed = ('google.com', 'recaptcha.net', 'hcaptcha.com')
        result['provider_host'] = host if any(provider_host(host, domain) for domain in allowed) else 'other'
        result['provider_path'] = address.path if re.fullmatch(r'/recaptcha/(?:api2|enterprise)/(?:anchor|bframe)', address.path) else 'other'
        result['title_challenge'] = 'challenge' in (locator.get_attribute('title', timeout=_observation_timeout(deadline)) or '').lower()
        result['src_recaptcha'] = 'recaptcha' in src
        result['size_normal'] = 'size=normal' in src
        result['in_visible_viewport'] = in_visible_viewport(locator, timeout=_observation_timeout(deadline))
        result.update(locator.evaluate("""el => {
            const box = el.getBoundingClientRect();
            const number = value => Math.round(Math.max(-1000000, Math.min(1000000, value)));
            let opacity = 1, hidden = false, undisplayed = false, clipped = false, modal = false;
            for (let node = el; node; node = node.parentElement) {
                const style = getComputedStyle(node);
                opacity *= Number(style.opacity);
                hidden ||= style.visibility !== 'visible';
                undisplayed ||= style.display === 'none';
                clipped ||= style.clipPath !== 'none' || style.clip !== 'auto';
                modal ||= node.getAttribute('aria-modal') === 'true' || node.getAttribute('role') === 'dialog' || node.tagName === 'DIALOG';
            }
            const left = Math.max(0, box.left), right = Math.min(innerWidth, box.right);
            const top = Math.max(0, box.top), bottom = Math.min(innerHeight, box.bottom);
            const intersects = right > left && bottom > top;
            const hit = intersects ? document.elementFromPoint((left + right) / 2, (top + bottom) / 2) : null;
            return {rect: {x:number(box.x), y:number(box.y), width:number(box.width), height:number(box.height)},
                viewport: {width:innerWidth, height:innerHeight}, effective_opacity: Math.round(opacity * 1000) / 1000,
                visibility_hidden:hidden, display_none:undisplayed, css_clip_present:clipped, ancestor_modal:modal,
                viewport_intersects:intersects, center_hit_iframe:hit === el};
        }""", timeout=_observation_timeout(deadline)))
        handle = locator.element_handle(timeout=_observation_timeout(deadline))
        frame = handle.content_frame() if handle else None
        if frame is not None:
            result['frame_dom_observed'] = True
            result['frame_host_matches_provider'] = (urlparse(frame.url).hostname or '').lower() == host
            checkboxes = frame.locator('#recaptcha-anchor, .recaptcha-checkbox, [role="checkbox"], input[type="checkbox"]')
            count = checkboxes.count()
            result['checkbox_present'] = count > 0
            result['checkbox_visible'] = any(in_visible_viewport(checkboxes.nth(i), timeout=_observation_timeout(deadline)) for i in range(min(count, 10)))
            result['checkbox_checked'] = any(checkboxes.nth(i).evaluate("el => el.checked === true || el.getAttribute('aria-checked') === 'true'", timeout=_observation_timeout(deadline)) for i in range(min(count, 10))) if count else None
            controls = frame.locator('.rc-imageselect, #recaptcha-verify-button, #audio-response, .rc-audiochallenge-input, .hcaptcha-challenge')
            control_count = controls.count()
            result['active_challenge_controls'] = any(in_visible_viewport(controls.nth(i), timeout=_observation_timeout(deadline)) for i in range(min(control_count, 10)))
            # A capped/incomplete scan must never qualify for settling grace.
            if count > 10 or control_count > 10:
                result['observation_incomplete'] = True
            body = frame.locator('body')
            if body.count() == 1:
                result['marker_ids'] = human_marker_ids(body.inner_text(timeout=_observation_timeout(deadline)), frame.url)
            else:
                result['observation_incomplete'] = True
    except _ChallengeObservationTimeout:
        raise
    except Exception:
        result['observation_incomplete'] = True
    return result


def challenge_reason(text, url=''):
    text = str(text).lower()
    if human_marker_ids(text, url):
        return 'human_verification_required'
    if any(x in text for x in ('two-factor', 'two factor', 'authentication code', 'verification code', 'одноразовый код', 'двухфактор')):
        return 'mfa_required'
    if any(x in text for x in ('link your account', 'link an existing account', 'associate your account')):
        return 'account_link_required'
    if any(x in text for x in ('неверный пароль', 'неверный логин', 'invalid username', 'incorrect password', 'incorrect email', 'bad username or password', 'invalid credentials', 'invalid sign in details', 'please check your orcid sign in details')):
        return 'invalid_credentials'
    if 'please enter a valid email address or orcid' in text:
        return 'invalid_username_format'
    if 'you will need to reactivate the account' in text:
        return 'account_reactivation_required'
    if 'ip_blocked' in url or 'заблокирован из-за нарушения' in text:
        return 'ip_blocked'
    return None


def _challenge_observation(page, *, form_submitted, deadline):
    """One read-only pass; return an error and whether it may settle naturally."""
    text = page_text(page, timeout=_observation_timeout(deadline))
    reason = challenge_reason(text, page.url)
    evidence = {'trigger': 'page_marker', 'marker_ids': human_marker_ids(text, page.url)} if reason == 'human_verification_required' else None
    if not form_submitted and reason in {'invalid_credentials', 'invalid_username_format'}:
        reason = None
    elif reason in {'invalid_credentials', 'invalid_username_format'} and provider_host(urlparse(page.url).hostname or '', 'orcid.org'):
        # ORCID's initial help text is not a server rejection. Its actual
        # validation messages live in mat-error / app-alert-message nodes.
        errors = page.locator('mat-error, app-alert-message, [role="alert"], #dialogTitle')
        reason = None
        for index in range(errors.count()):
            _observation_timeout(deadline)
            error = errors.nth(index)
            if error.is_visible():
                reason = challenge_reason(error.inner_text(timeout=_observation_timeout(deadline)))
                if reason:
                    break
    # An embedded challenge script alone is not a challenge. Only visible forms count.
    # The ubiquitous invisible reCAPTCHA badge is not an interactive challenge.
    selector = 'iframe[title*="challenge" i], iframe[src*="recaptcha"][src*="size=normal"]'
    if reason:
        return reason, evidence, False
    pending = None
    frames = page.locator(selector)
    for index in range(frames.count()):
        frame = frames.nth(index)
        if not in_visible_viewport(frame, timeout=_observation_timeout(deadline)):
            continue
        observed = challenge_frame_evidence(frame, deadline=deadline)
        evidence = {'trigger': 'iframe_title' if observed.get('title_challenge') else 'recaptcha_normal_widget', 'frame': observed}
        loading = (
            provider_host(observed.get('provider_host', ''), 'hcaptcha.com')
            and observed.get('title_challenge') is True
            and observed.get('frame_dom_observed') is True
            and observed.get('frame_host_matches_provider') is True
            and observed.get('checkbox_present') is False
            and observed.get('checkbox_visible') is False
            and observed.get('active_challenge_controls') is False
            and observed.get('marker_ids') == []
            and not observed.get('observation_incomplete')
        )
        if not loading:
            return 'human_verification_required', evidence, False
        # Inspect every other visible frame before waiting: an interactive
        # challenge must fail immediately even beside an automatic loader.
        pending = pending or evidence
    return ('human_verification_required', pending, True) if pending else (None, None, False)


def assert_no_challenge(page, *, form_submitted=True):
    """Allow only bounded, passive observation of known automatic verification.

    A single deadline covers every frame and every observation in this call.
    Disappearance is readiness only; callers must still prove authentication.
    """
    deadline = time.monotonic() + CHALLENGE_SETTLE_SECONDS
    pending = None
    while True:
        try:
            reason, evidence, may_settle = _challenge_observation(page, form_submitted=form_submitted, deadline=deadline)
        except _ChallengeObservationTimeout:
            reason = 'human_verification_required' if pending else 'challenge_observation_incomplete'
            evidence, may_settle = pending, True
        except Exception:
            raise AuthFailure('challenge_observation_incomplete', verification_evidence={'trigger': 'observation_incomplete'}) from None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure_reason = reason or ('human_verification_required' if pending else 'challenge_observation_incomplete')
            observed = evidence or pending or {'trigger': 'observation_deadline'}
            raise AuthFailure(failure_reason, verification_evidence={**observed, 'settling': 'timed_out'}) from None
        if not reason:
            return
        if not may_settle:
            if pending is not None and evidence is not None:
                evidence = {**evidence, 'settling': 'stopped_by_guard'}
            raise AuthFailure(reason, verification_evidence=evidence)
        pending = evidence
        # No click, submission, navigation, token mutation or challenge solving.
        page.wait_for_timeout(min(CHALLENGE_POLL_SECONDS, remaining) * 1000)


def verify_browser_egress(context):
    if os.environ.get('HOME_VPN_REQUIRED') != '1':
        return
    try:
        expected = Path(os.environ['HOME_VPN_EXPECTED_IP_FILE']).read_text().strip()
        page = context.new_page()
        try:
            response = page.goto('https://api.ipify.org?format=json', wait_until='domcontentloaded', timeout=30000)
            observed = response.json().get('ip') if response else None
        finally:
            page.close()
    except Exception:
        raise AuthFailure('vpn_verification_failed') from None
    if not expected or observed != expected:
        raise AuthFailure('vpn_route_mismatch')


def visible(page, selectors):
    for selector in selectors:
        locator = page.locator(selector)
        for index in range(locator.count()):
            item = locator.nth(index)
            if item.is_visible():
                return item
    return None


def click_named(page, pattern):
    for role in ('button', 'link'):
        locator = page.get_by_role(role, name=re.compile(pattern, re.I))
        for index in range(locator.count()):
            item = locator.nth(index)
            if item.is_visible() and item.is_enabled():
                item.click(timeout=15000)
                return True
    return False


def wait_navigation(page):
    try:
        page.wait_for_load_state('domcontentloaded', timeout=15000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1000)
    except Exception:
        if not page.is_closed():
            raise


def elibrary_authenticated(page):
    text = page_text(page)
    session = page.locator('#win_session')
    session_text = session.text_content() if session.count() else ''
    anonymous = re.search(r'Незарегистрированный пользователь|Вы не авторизованы', text + (session_text or ''), re.I)
    named_session = bool(re.search(r'Имя пользователя:\s*\S', session_text or ''))
    return not anonymous and (named_session or bool(re.search(r'\b(?:Выход|Выйти)\b', text, re.I)))


@diagnostic_login
def login_elibrary(context):
    username = os.environ.get('ELIBRARY_USERNAME', '')
    password = os.environ.get('ELIBRARY_PASSWORD', '')
    if not username or not password:
        raise AuthFailure('credentials_missing')
    page = context.new_page()
    page.goto('https://elibrary.ru/defaultx.asp', wait_until='domcontentloaded', timeout=90000)
    wait_navigation(page)
    assert_no_challenge(page)
    user = visible(page, ['input[name="login"]', '#login', 'input[autocomplete="username"]'])
    if user is None:
        toggle = visible(page, ['span[title*="Вход в библиотеку"]'])
        if toggle is not None:
            toggle.click()
            page.wait_for_timeout(600)
        user = visible(page, ['input[name="login"]', '#login'])
    secret = visible(page, ['input[name="password"]', 'input[type="password"]'])
    if user is None or secret is None:
        raise AuthFailure('login_form_changed')
    if urlparse(page.url).hostname not in {'elibrary.ru', 'www.elibrary.ru'}:
        raise AuthFailure('unexpected_login_origin')
    user.fill(username)
    secret.fill(password)
    if not click_named(page, r'^Вход$|^Войти$|^Login$|^Sign in$'):
        submit = visible(page, ['[onclick="check_all()"]', 'input[type="submit"]', 'input[type="image"][alt*="Вход"]', '[onclick*="login()"]'])
        if submit is None:
            raise AuthFailure('login_submit_changed')
        submit.click()
    for _ in range(30):
        wait_navigation(page)
        assert_no_challenge(page)
        if elibrary_authenticated(page):
            return page
    raise AuthFailure('login_not_confirmed')


def wos_account_names():
    """Account label candidates come from the portfolio's configured identity."""
    import yaml
    config = Path(__file__).resolve().parents[1] / 'config' / 'profile.yml'
    try:
        profile = (yaml.safe_load(config.read_text(encoding='utf-8')) or {}).get('profile', {})
    except (OSError, ValueError, yaml.YAMLError):
        return set()
    names = {str(profile.get(key) or '').strip() for key in ('display_name_en', 'display_name_ru')}
    names.update(str(name).strip() for name in profile.get('aliases', []) if isinstance(name, str))
    # WoS commonly omits the middle initial displayed by the portfolio.
    names.update(re.sub(r'\s+[A-Za-zА-Яа-яЁё]\.\s+', ' ', name) for name in tuple(names))
    return {name for name in names if name}


def wos_logout_visible(page):
    pattern = re.compile(r'^\s*(?:(?:logout|exit_to_app)\s+)?(?:Sign out|Log out|End session|Выйти|Выход|Завершить сеанс(?: и выйти)?)\s*$', re.I)
    for role in ('button', 'link', 'menuitem'):
        controls = page.get_by_role(role, name=pattern)
        if any(controls.nth(index).is_visible() for index in range(controls.count())):
            return True
    return bool(visible(page, ['a[href*="signout"]', 'a[href*="logout"]']))


def wos_authenticated(page):
    # The user menu is positive session proof; SID existence is not.
    if wos_logout_visible(page):
        return True
    account = visible(page, [
        'button[data-ta="wos-header-user_name"]',
        '[data-ta="user-menu"]', '[data-ta="user-menu-button"]',
        'button[aria-label*="user menu" i]', 'button[aria-label*="account menu" i]',
    ])
    if account is not None and account.is_enabled():
        account.click(timeout=15000)
        for _ in range(10):
            if wos_logout_visible(page):
                return True
            page.wait_for_timeout(200)
        return False
    # A matching public author label alone is insufficient: open only the
    # configured user's account button and confirm the session's logout action.
    for name in sorted(wos_account_names()):
        buttons = page.get_by_role('button', name=name, exact=True)
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if not button.is_visible() or not button.is_enabled():
                continue
            button.click(timeout=15000)
            for _ in range(10):
                if wos_logout_visible(page):
                    return True
                page.wait_for_timeout(200)
            return False
    return False


def provider_host(host, provider):
    return host == provider or host.endswith('.' + provider)


def normalize_orcid_username(value):
    """Undo the user's Markdown escape only; never transform the password."""
    return value.strip().replace('\\@', '@')


def valid_orcid_username(value):
    return bool(re.fullmatch(r'[^@\s\\]+@[^@\s\\]+\.[^@\s\\]+', value) or re.fullmatch(r'(?:\d{4}-){3}\d{3}[\dXx]|\d{15}[\dXx]', value))


def orcid_auth_response_evidence(status, payload):
    """ORCID's public SignIn interface: retain only status and boolean flags."""
    evidence = {'http_status': int(status), 'response_observed': True}
    if not 200 <= status < 300:
        evidence['reason'] = f'orcid_auth_http_{status}'
        return evidence
    if not isinstance(payload, dict):
        evidence['reason'] = 'orcid_auth_response_unrecognized'
        return evidence
    mapping = {'verificationCodeRequired': 'mfa_required', 'disabled': 'account_reactivation_required', 'unclaimed': 'account_claim_required', 'deprecated': 'account_deprecated', 'invalidUserType': 'account_type_unsupported'}
    for key in ('success', *mapping):
        if key in payload:
            evidence[key] = payload[key] is True or str(payload[key]).lower() == 'true'
    evidence['reason'] = next((reason for key, reason in mapping.items() if evidence.get(key)), None)
    if not evidence['reason'] and evidence.get('success') is False:
        # A negative result alone does not distinguish credentials from other
        # server-side failures. Only an explicit UI marker establishes that.
        evidence['reason'] = 'orcid_signin_rejected'
    return evidence


def choose_orcid_signin(page, host):
    """Never confuse the author's public ORCID link with the SSO login option."""
    if provider_host(host, 'clarivate.com'):
        control = visible(page, ['a[href*="orcid" i]', 'button[title*="orcid" i]', '[aria-label*="orcid" i]'])
        if control is not None:
            control.click()
            return True
        return click_named(page, r'ORCID')
    # In a WoS inline login dialog only an explicit sign-in affordance counts.
    return click_named(page, r'sign in (?:with|using) ORCID|ORCID sign in')


@diagnostic_login
def login_wos(context, profile_url, timeout=180):
    evidence = {'submit_clicked': False, 'input_matches_configured': False}
    try:
        return _login_wos(context, profile_url, timeout, evidence)
    except Exception as exc:
        failure = exc if isinstance(exc, AuthFailure) else AuthFailure(type(exc).__name__)
        failure.authentication_evidence = {**evidence, **(failure.authentication_evidence or {})}
        raise failure from None


def _login_wos(context, profile_url, timeout, evidence):
    configured_username = os.environ.get('WOS_ORCID_USERNAME', '')
    username = normalize_orcid_username(configured_username)
    password = os.environ.get('WOS_ORCID_PASSWORD', '')
    if not username or not password:
        raise AuthFailure('credentials_missing')
    evidence['username_format_valid'] = valid_orcid_username(username)
    evidence['username_normalized'] = username != configured_username
    if not evidence['username_format_valid']:
        raise AuthFailure('username_configuration_invalid')
    page = context.new_page()
    page.goto('https://www.webofscience.com/', wait_until='domcontentloaded', timeout=90000)
    deadline = time.monotonic() + timeout
    submitted = False
    selected_signin = False
    selected_orcid = False
    auth_responses = []

    def record_auth_response(response):
        try:
            address = urlparse(response.url)
            if not provider_host(address.hostname or '', 'orcid.org') or address.path not in {'/signin/auth.json', '/login'} or response.request.method != 'POST':
                return
            try:
                payload = response.json()
            except Exception:
                payload = None
            auth_responses.append(orcid_auth_response_evidence(response.status, payload))
        except Exception:
            pass

    context.on('response', record_auth_response)
    while time.monotonic() < deadline:
        if page.is_closed():
            page = context.pages[0]
        wait_navigation(page)
        if page.is_closed():
            page = context.pages[0]
            continue
        if auth_responses and auth_responses[-1].get('reason'):
            reason = auth_responses[-1]['reason']
            if reason == 'orcid_signin_rejected':
                # The JSON response arrives before Angular renders its error.
                # Give the explicit UI message a bounded opportunity to appear.
                page.wait_for_timeout(1500)
                try:
                    assert_no_challenge(page)
                except AuthFailure as failure:
                    failure.authentication_evidence = auth_responses[-1]
                    raise
            raise AuthFailure(reason, authentication_evidence=auth_responses[-1])
        assert_no_challenge(page, form_submitted=submitted)
        dismiss = visible(page, ['#onetrust-reject-all-handler', '#onetrust-accept-btn-handler'])
        if dismiss is not None:
            dismiss.click()
        host = urlparse(page.url).hostname or ''
        if provider_host(host, 'clarivate.com'):
            # WoS sometimes redirects the homepage straight to its sign-in
            # service. Do not submit the unused Clarivate password form first.
            selected_signin = True
        if provider_host(host, 'orcid.org'):
            user = visible(page, ['#username-input', '#userId', 'input[name="username"]', 'input[name="userId"]', 'input[autocomplete="username"]', 'input[type="email"]'])
            secret = visible(page, ['#password', 'input[type="password"]'])
            if user is not None and secret is not None and not submitted:
                user.fill(username)
                secret.fill(password)
                evidence['input_matches_configured'] = user.input_value() == username
                if not evidence['input_matches_configured']:
                    raise AuthFailure('username_input_not_applied')
                # Live ORCID form: button#signin-button, "Sign in to ORCID".
                # Its cookie banner may mount after the fields have appeared.
                consent = visible(page, ['#onetrust-reject-all-handler', '#onetrust-accept-btn-handler'])
                if consent is not None:
                    consent.click()
                submit = visible(page, ['button#signin-button[type="submit"]'])
                if submit is not None:
                    submit.click(timeout=15000)
                elif not click_named(page, r'^Sign in(?: to ORCID)?$|^Войти(?: в ORCID)?$'):
                    raise AuthFailure('orcid_submit_changed')
                submitted = True
                evidence['submit_clicked'] = True
                continue
            # The authorization page is the standard ORCID OAuth consent for WoS.
            if (submitted or selected_orcid) and click_named(page, r'^Authorize(?: access)?$|^Разрешить доступ$'):
                continue
        elif provider_host(host, 'webofscience.com') and wos_authenticated(page):
            page.goto(profile_url, wait_until='domcontentloaded', timeout=90000)
            return page
        elif not selected_signin:
            if click_named(page, r'^Sign in$|^Sign in.*Web of Science|^Войти$'):
                selected_signin = True
                continue
        if selected_signin and not selected_orcid:
            if choose_orcid_signin(page, host):
                selected_orcid = True
            else:
                # The actual submenu is an <a> without href in the current WoS
                # DOM, so its implicit accessibility role is not necessarily link.
                signin_link = page.locator('a').filter(has_text=re.compile(r'^\s*Sign in\s*$', re.I))
                for index in range(signin_link.count()):
                    item = signin_link.nth(index)
                    if item.is_visible():
                        item.click()
                        break
            if selected_orcid:
                page.wait_for_timeout(1000)
                # Some sign-in variants open the identity provider in a popup.
                if len(context.pages) > 1:
                    page = context.pages[-1]
                continue
        # ORCID may close a popup when redirecting the original tab.
        if page.is_closed():
            page = context.pages[0]
    raise AuthFailure('wos_login_not_confirmed' if submitted else 'wos_login_form_changed', authentication_evidence=auth_responses[-1] if auth_responses else {'response_observed': False, 'submit_clicked': submitted})
