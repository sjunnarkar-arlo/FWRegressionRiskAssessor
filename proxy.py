#!/usr/bin/env python3
"""
Dev proxy: serves static files + forwards /mcp/* to Arlochat internal ALB.
Run: python proxy.py
Then open: http://localhost:8082/firmware-regression-assessor.html
"""

import http.server
import socketserver
import threading
import urllib.request
import urllib.error
import urllib.parse
import ssl
import os

PORT   = 8082
TARGET = 'https://internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080'

# Accept self-signed / internal certs
_ssl = ssl.create_default_context()
_ssl.check_hostname = False
_ssl.verify_mode = ssl.CERT_NONE


def _rewrite_endpoint(data, port):
    """Rewrite ALB session URL so the browser POSTs back through our proxy."""
    parsed = urllib.parse.urlparse(data)
    if parsed.scheme:  # absolute URL from ALB
        qs = ('?' + parsed.query) if parsed.query else ''
        return 'http://localhost:{}/mcp{}{}'.format(port, parsed.path, qs)
    else:              # relative path like /session?sessionId=xyz
        path = data if data.startswith('/') else '/' + data
        return 'http://localhost:{}/mcp{}'.format(port, path)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('[proxy] ' + (fmt % args), flush=True)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/mcp'):
            self._proxy_sse()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/mcp'):
            self._proxy_post()
        else:
            self.send_error(404)

    def _cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept')

    def _proxy_sse(self):
        target_path = self.path[4:] or '/sse'
        url = TARGET + target_path
        print('[proxy] SSE -> ' + url, flush=True)

        req = urllib.request.Request(url, headers={'Accept': 'text/event-stream'})
        try:
            upstream = urllib.request.urlopen(req, context=_ssl, timeout=120)
        except Exception as e:
            print('[proxy] SSE connect error: ' + str(e), flush=True)
            self.send_error(502, str(e))
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self._cors_headers()
        self.end_headers()

        current_event = ''
        try:
            while True:
                raw = upstream.readline()
                if not raw:
                    break
                line = raw.decode('utf-8')

                if line.startswith('event:'):
                    current_event = line[6:].strip()
                    self.wfile.write(raw)

                elif line.startswith('data:') and current_event == 'endpoint':
                    data = line[5:].strip()
                    rewritten = _rewrite_endpoint(data, PORT)
                    print('[proxy] endpoint rewritten -> ' + rewritten, flush=True)
                    self.wfile.write(('data: ' + rewritten + '\n').encode())
                    current_event = ''

                else:
                    self.wfile.write(raw)

                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print('[proxy] SSE stream error: ' + str(e), flush=True)

    def _proxy_post(self):
        target_path = self.path[4:]
        url = TARGET + target_path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''
        print('[proxy] POST -> ' + url, flush=True)
        req = urllib.request.Request(
            url, data=body, method='POST',
            headers={'Content-Type': 'application/json'}
        )
        try:
            r = urllib.request.urlopen(req, context=_ssl, timeout=30)
            payload = r.read()
            self.send_response(r.status)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(payload)
        except urllib.error.HTTPError as e:
            payload = e.read()
            self.send_response(e.code)
            self._cors_headers()
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            self.send_error(502, str(e))


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with ThreadedTCPServer(('', PORT), Handler) as srv:
        print('Proxy running: http://localhost:{}/firmware-regression-assessor.html'.format(PORT))
        print('Forwarding /mcp/* to ' + TARGET)
        print('Press Ctrl+C to stop.')
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print('Stopped.')
