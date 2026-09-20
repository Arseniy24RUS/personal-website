#!/usr/bin/env python3
"""Local static preview with enough connection backlog for parallel browsers."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class PreviewServer(ThreadingHTTPServer):
    # socketserver defaults to five queued connections in Python 3.12. Parallel
    # Chromium contexts can burst past this and receive ERR_CONNECTION_REFUSED
    # before otherwise healthy local assets ever reach the request handler.
    request_queue_size = 128


class PreviewHandler(SimpleHTTPRequestHandler):
    def log_request(self, code='-', size='-'):
        if str(code).startswith(('4', '5')):
            super().log_request(code, size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    args = parser.parse_args()
    with PreviewServer(('127.0.0.1', args.port), PreviewHandler) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
