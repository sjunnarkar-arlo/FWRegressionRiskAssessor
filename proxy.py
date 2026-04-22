#!/usr/bin/env python3
"""
Dev proxy: serves static files + forwards /mcp/* to Arlochat internal ALB.
Run: python proxy.py
Then open: http://localhost:8082/firmware-regression-assessor.html
"""

import http.server
import socketserver
import os
import traceback
import requests

PORT   = 8082
TARGET = 'http://internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080'


def _rewrite_endpoint(data, port):
    """Rewrite ALB session URL so browser POSTs come back through the proxy."""
    from urllib.parse import urlparse
    parsed = urlparse(data.strip())
    if parsed.scheme:
        qs = ('?' + parsed.query) if parsed.query else ''
        return 'http://localhost:{}/mcp{}{}'.format(port, parsed.path, qs)
    path = data.strip()
    if not path.startswith('/'):
        path = '/' + path
    return 'http://localhost:{}/mcp{}'.format(port, path)


class Handler(http.server.SimpleHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print('[proxy] ' + (fmt % args), flush=True)

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/mcp'):
            self._sse()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/mcp'):
            self._post()
        else:
            self.send_error(404)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept')

    def _sse(self):
        try:
            self._sse_inner()
        except Exception:
            traceback.print_exc()

    def _sse_inner(self):
        path = self.path[4:] or '/sse'
        url  = TARGET + path
        print('[proxy] SSE -> ' + url, flush=True)

        try:
            upstream = requests.get(
                url,
                headers={'Accept': 'text/event-stream'},
                stream=True,
                timeout=120
            )
            upstream.raise_for_status()
        except Exception as e:
            print('[proxy] SSE connect failed: ' + str(e), flush=True)
            self.send_error(502, str(e))
            return

        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self._cors()
        self.end_headers()

        current_event = ''
        try:
            for raw in upstream.iter_lines(chunk_size=1, decode_unicode=True, keepends=True):
                if raw is None:
                    continue
                line = raw if isinstance(raw, str) else raw.decode('utf-8')

                if line.startswith('event:'):
                    current_event = line[6:].strip()
                    self.wfile.write(line.encode('utf-8'))

                elif line.startswith('data:') and current_event == 'endpoint':
                    data = line[5:].strip()
                    rewritten = _rewrite_endpoint(data, PORT)
                    print('[proxy] endpoint -> ' + rewritten, flush=True)
                    self.wfile.write(('data: ' + rewritten + '\n').encode('utf-8'))
                    current_event = ''

                else:
                    self.wfile.write(line.encode('utf-8'))

                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print('[proxy] SSE stream error: ' + str(e), flush=True)

    def _post(self):
        path = self.path[4:]
        url  = TARGET + path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''
        print('[proxy] POST -> ' + url, flush=True)
        try:
            r = requests.post(url, data=body, headers={'Content-Type': 'application/json'}, timeout=30)
            self.send_response(r.status_code)
            self._cors()
            self.end_headers()
            self.wfile.write(r.content)
        except Exception as e:
            print('[proxy] POST error: ' + str(e), flush=True)
            self.send_error(502, str(e))


class ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    with ThreadedServer(('', PORT), Handler) as srv:
        print('Proxy running: http://localhost:{}/firmware-regression-assessor.html'.format(PORT))
        print('Forwarding /mcp/* to ' + TARGET)
        print('Press Ctrl+C to stop.')
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print('Stopped.')
