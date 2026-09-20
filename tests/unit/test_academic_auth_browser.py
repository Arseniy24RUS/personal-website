"""Exercise ordinary login with a real browser and local, mocked provider pages.

No external requests or real credentials. These tests validate locator and
redirect behavior; the actual providers still require the Actions live test.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import provider_auth as auth


class AuthBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
            cls.playwright = sync_playwright().start()
            args = {'headless': True}
            if not Path(cls.playwright.chromium.executable_path).exists():
                edge = Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
                if not edge.exists():
                    cls.playwright.stop()
                    raise unittest.SkipTest('Install Playwright Chromium for browser authentication tests')
                args['executable_path'] = str(edge)
            cls.browser = cls.playwright.chromium.launch(**args)
        except ImportError:
            raise unittest.SkipTest('Playwright is not installed')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()

    def tearDown(self):
        self.context.close()

    def test_elibrary_homepage_form_then_named_session(self):
        def route(request):
            if request.request.url.endswith('start_session.asp'):
                html = '<body><div id="win_session">Имя пользователя: Test Researcher</div>Личный кабинет</body>'
            else:
                html = '''<body><form method="post" action="/start_session.asp">
                    <input name="login"><input name="password" type="password">
                    <div onclick="check_all()">Вход</div></form>
                    <script>function check_all(){document.querySelector('form').submit()}</script></body>'''
            request.fulfill(status=200, content_type='text/html; charset=utf-8', body=html)
        self.context.route('**/*', route)
        with patch.dict(os.environ, {'ELIBRARY_USERNAME': 'fixture-user', 'ELIBRARY_PASSWORD': 'fixture-password'}):
            page = auth.login_elibrary(self.context)
        self.assertTrue(auth.elibrary_authenticated(page))
        self.assertTrue(page.url.endswith('start_session.asp'))

    def test_elibrary_anonymous_session_is_not_authentication(self):
        page = self.context.new_page()
        page.set_content('<body><div id="win_session">Имя пользователя: Незарегистрированный пользователь</div>Личный кабинет Закрыть сессию</body>')
        self.assertFalse(auth.elibrary_authenticated(page))

    def test_wos_signin_menu_orcid_callback(self):
        visited = []
        authenticated = False
        profile_url = 'https://www.webofscience.com/wos/author/record/TEST'

        def route(request):
            nonlocal authenticated
            url = request.request.url
            visited.append(url)
            if url.startswith('https://access.clarivate.com/'):
                html = '<body><a href="https://orcid.org/oauth/authorize">Sign in with ORCID</a></body>'
            elif url == 'https://orcid.org/finish':
                authenticated = True
                html = f'<body><script>location.href="{profile_url}"</script></body>'
            elif url.startswith('https://orcid.org/oauth/'):
                html = '''<body><form method="post" action="/finish"><input id="username-input"><input type="password"><button id="signin-button" type="submit">Sign in to ORCID</button></form></body>'''
            elif authenticated:
                html = '<body><button data-ta="user-menu">Account</button><p>Author works</p></body>'
            else:
                html = '''<body><button onclick="document.querySelector('#submenu').hidden=false">Sign In</button>
                    <a id="submenu" hidden onclick="location.href='https://access.clarivate.com/login'">Sign In</a>
                    <a href="https://orcid.org/0000-public-record">ORCID</a></body>'''
            request.fulfill(status=200, content_type='text/html', body=html)

        self.context.route('**/*', route)
        with patch.dict(os.environ, {'WOS_ORCID_USERNAME': 'fixture-user', 'WOS_ORCID_PASSWORD': 'fixture-password'}):
            page = auth.login_wos(self.context, profile_url, timeout=30)
        self.assertTrue(auth.wos_authenticated(page))
        self.assertFalse(any('0000-public-record' in url for url in visited))
        self.assertTrue(any('access.clarivate.com/login' in url for url in visited))
        self.assertTrue(any('orcid.org/oauth' in url for url in visited))
        self.assertEqual(visited[0], 'https://www.webofscience.com/')

    def test_captcha_is_explicit_and_not_interacted_with(self):
        page = self.context.new_page()
        page.set_content('<body>Please verify you are human<button>Continue</button></body>')
        with self.assertRaisesRegex(auth.AuthFailure, '^human_verification_required$'):
            auth.assert_no_challenge(page)

    def test_wos_direct_clarivate_redirect_chooses_orcid_first(self):
        visited = []
        authenticated = False
        profile_url = 'https://www.webofscience.com/wos/author/record/TEST'

        def route(request):
            nonlocal authenticated
            url = request.request.url
            visited.append(url)
            if url == 'https://www.webofscience.com/':
                html = '<body><script>location.href="https://access.clarivate.com/login"</script></body>'
            elif url.startswith('https://access.clarivate.com/'):
                html = '<body><form action="https://invalid.test/empty-password"><button>Sign In</button></form><a href="https://orcid.org/oauth/authorize">ORCID</a></body>'
            elif url == 'https://orcid.org/finish':
                authenticated = True
                html = f'<body><script>location.href="{profile_url}"</script></body>'
            elif url.startswith('https://orcid.org/oauth/'):
                html = '<body><form method="post" action="/finish"><input id="username-input"><input type="password"><button>Sign in</button></form></body>'
            elif authenticated:
                html = '<body><button data-ta="user-menu">Account</button></body>'
            else:
                html = '<body>Unexpected route</body>'
            request.fulfill(status=200, content_type='text/html', body=html)

        self.context.route('**/*', route)
        with patch.dict(os.environ, {'WOS_ORCID_USERNAME': 'fixture-user', 'WOS_ORCID_PASSWORD': 'fixture-password'}):
            page = auth.login_wos(self.context, profile_url, timeout=30)
        self.assertTrue(auth.wos_authenticated(page))
        self.assertFalse(any('invalid.test' in url for url in visited))

    def test_diagnostics_exclude_form_values_and_url_query(self):
        self.context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<body>Private body token<input name="username" value="private-login"><input type="password" value="private-password"><button>Sign In</button></body>'))
        page = self.context.new_page()
        page.goto('https://orcid.org/oauth/authorize?token=private-query#private-fragment')
        diagnostics = str(auth.safe_browser_diagnostics(self.context))
        for secret in ('private-login', 'private-password', 'Private body token', 'private-query', 'private-fragment'):
            self.assertNotIn(secret, diagnostics)
        self.assertIn('username', diagnostics)


if __name__ == '__main__':
    unittest.main()
