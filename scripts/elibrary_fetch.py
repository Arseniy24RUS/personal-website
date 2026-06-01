from __future__ import annotations

from http.cookiejar import CookieJar
import os
import time
import urllib.error
import urllib.request

DEFAULT_PREFLIGHT_URL = 'https://www.elibrary.ru/defaultx.asp'
DEFAULT_TIMEOUT = 45
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Connection': 'close',
}


def build_opener() -> tuple[urllib.request.OpenerDirector, CookieJar]:
    jar = CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    proxy_url = os.environ.get('ELIBRARY_PROXY_URL')
    if proxy_url:
        handlers.insert(0, urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url}))
    return urllib.request.build_opener(*handlers), jar


def fetch_once(opener: urllib.request.OpenerDirector, url: str, *, referer: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> tuple[str | None, dict]:
    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers['Referer'] = referer
    extra_cookie = os.environ.get('ELIBRARY_COOKIE')
    if extra_cookie:
        headers['Cookie'] = extra_cookie
    started = time.time()
    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            enc = resp.headers.get_content_charset() or 'utf-8'
            return raw.decode(enc, errors='replace'), {
                'status': 'ok',
                'http_status': resp.status,
                'elapsed_sec': round(time.time() - started, 3),
                'content_length': len(raw),
                'url': url,
                'final_url': resp.geturl(),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')[:1200]
        return None, {
            'status': 'http_error',
            'http_status': exc.code,
            'elapsed_sec': round(time.time() - started, 3),
            'url': url,
            'error_excerpt': body,
        }
    except Exception as exc:
        return None, {
            'status': 'error',
            'elapsed_sec': round(time.time() - started, 3),
            'url': url,
            'error': repr(exc),
        }


def fetch_elibrary_page(url: str) -> tuple[str | None, dict]:
    opener, jar = build_opener()
    preflight_url = os.environ.get('ELIBRARY_PREFLIGHT_URL', DEFAULT_PREFLIGHT_URL)
    preflight_text, preflight_report = fetch_once(opener, preflight_url, referer='https://www.elibrary.ru/')
    text, target_report = fetch_once(opener, url, referer=preflight_url)
    target_report['preflight'] = {
        'status': preflight_report.get('status'),
        'http_status': preflight_report.get('http_status'),
        'content_length': preflight_report.get('content_length'),
        'final_url': preflight_report.get('final_url'),
        'cookies_after_preflight': len(jar),
        'has_cookie_warning_text': bool(preflight_text and ('cookie' in preflight_text.lower() or 'cookies' in preflight_text.lower())),
    }
    target_report['cookies_count'] = len(jar)
    if text:
        lowered = text.lower()
        target_report['html_fingerprint'] = {
            'has_suspicious_ip_text': 'подозр' in lowered or 'suspicious' in lowered or 'ip_blocked' in lowered,
            'has_cookie_text': 'cookie' in lowered or 'cookies' in lowered,
            'content_length': len(text.encode('utf-8', errors='replace')),
            'excerpt': text[:500].replace('\n', ' '),
        }
    return text, target_report
