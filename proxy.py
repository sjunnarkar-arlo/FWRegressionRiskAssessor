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
import json
import time

PORT   = 8082
TARGET = 'http://internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com:8080'

# ── DEBUG HELPERS ────────────────────────────────────────────────────────────
TRUNCATE = 400   # max chars shown for response previews

def _fmt(s, limit=TRUNCATE):
    """Truncate + flatten a string for single-line log output."""
    s = str(s).replace('\n', ' ').replace('\r', '')
    return s[:limit] + ('…' if len(s) > limit else '')

def _log_call(body_bytes, resp_bytes, elapsed_ms):
    """Parse a JSON-RPC body and its response; emit structured debug lines."""
    try:
        req = json.loads(body_bytes)
    except Exception:
        print(f'[mcp]  (unparseable body: {body_bytes[:80]})', flush=True)
        return

    method = req.get('method', '?')

    # Skip noisy handshake noise
    if method in ('initialize', 'notifications/initialized'):
        return

    if method == 'tools/call':
        name = req.get('params', {}).get('name', '?')
        args = req.get('params', {}).get('arguments', {})
        args_s = _fmt(json.dumps(args, separators=(',', ':')), 250)
        print(f'[mcp] CALL  {name}  args={args_s}  ({elapsed_ms}ms)', flush=True)

        try:
            resp = json.loads(resp_bytes)
            err = resp.get('error')
            if err:
                print(f'[mcp]   ERROR  {err}', flush=True)
                return
            content = resp.get('result', {}).get('content', [])
            text = '\n'.join(c.get('text', '') for c in content if c.get('type') == 'text')
            print(f'[mcp]   OK  {len(text)} chars  preview={_fmt(text)}', flush=True)
        except Exception as e:
            raw_preview = _fmt(resp_bytes.decode('utf-8', errors='replace'))
            print(f'[mcp]   resp(raw)={raw_preview}  parse_err={e}', flush=True)

    elif method == 'tools/list':
        try:
            resp = json.loads(resp_bytes)
            tools = [t.get('name', '?') for t in resp.get('result', {}).get('tools', [])]
            print(f'[mcp] tools/list -> [{", ".join(tools)}]', flush=True)
        except Exception:
            print(f'[mcp] tools/list  ({elapsed_ms}ms)', flush=True)

    else:
        print(f'[mcp] {method}  ({elapsed_ms}ms)', flush=True)


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
            for raw in upstream.iter_lines(chunk_size=1, decode_unicode=True):
                if raw is None:
                    continue
                line = raw if isinstance(raw, str) else raw.decode('utf-8')

                if line.startswith('event:'):
                    current_event = line[6:].strip()
                    self.wfile.write((line + '\n').encode('utf-8'))

                elif line.startswith('data:') and current_event == 'endpoint':
                    data = line[5:].strip()
                    rewritten = _rewrite_endpoint(data, PORT)
                    print('[proxy] endpoint -> ' + rewritten, flush=True)
                    self.wfile.write(('data: ' + rewritten + '\n').encode('utf-8'))
                    current_event = ''

                elif line.startswith('data:') and line.strip() != 'data:':
                    # Log SSE push events (JSON-RPC responses the server sends back proactively)
                    payload = line[5:].strip()
                    if len(payload) > 10:  # skip empty pings
                        try:
                            msg = json.loads(payload)
                            # Only log tool result push events; skip routine acks
                            if 'result' in msg or 'error' in msg:
                                preview = _fmt(payload)
                                print(f'[sse]  push id={msg.get("id","?")}  {preview}', flush=True)
                        except Exception:
                            pass
                    self.wfile.write((line + '\n').encode('utf-8'))

                else:
                    self.wfile.write((line + '\n').encode('utf-8'))

                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            print('[proxy] SSE stream error: ' + str(e), flush=True)

    def _post(self):
        path = self.path[4:]
        url  = TARGET + path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else b''
        t0 = time.time()
        try:
            r = requests.post(url, data=body, headers={'Content-Type': 'application/json'}, timeout=120)
            elapsed = int((time.time() - t0) * 1000)
            _log_call(body, r.content, elapsed)
            self.send_response(r.status_code)
            self._cors()
            self.end_headers()
            self.wfile.write(r.content)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # browser closed the connection before we could respond
        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            print(f'[proxy] POST error ({elapsed}ms): {e}', flush=True)
            try:
                self.send_error(502, str(e))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass


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
