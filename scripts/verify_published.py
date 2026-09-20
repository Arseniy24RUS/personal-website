#!/usr/bin/env python3
"""Compare deployed public JSON with the validated local publication."""
import argparse
import hashlib
from pathlib import Path
import time
import urllib.request

FILES = ('data/public/profile.json', 'data/public/publications.json', 'data/media/published.json', 'data/media/published-fallback.json')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', type=int, default=0)
    parser.add_argument('--base-url', default='https://sitkovskiy.ru')
    args = parser.parse_args()
    expected = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in FILES}
    deadline = time.monotonic() + args.wait
    while True:
        good = []
        for name, digest in expected.items():
            try:
                request = urllib.request.Request(f'{args.base_url.rstrip("/")}/{name}?verify={digest[:12]}', headers={'Cache-Control': 'no-cache', 'User-Agent': 'PortfolioDeploymentCheck/1.0'})
                with urllib.request.urlopen(request, timeout=20) as response:
                    actual = hashlib.sha256(response.read()).hexdigest()
                good.append(actual == digest)
            except Exception:
                good.append(False)
        if all(good):
            print('Published profile, publications and both media snapshots match validated output.')
            return
        if time.monotonic() >= deadline:
            raise SystemExit('Published data does not yet match this validated commit.')
        time.sleep(min(15, max(0, deadline - time.monotonic())))

if __name__ == '__main__':
    main()
