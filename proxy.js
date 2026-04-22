#!/usr/bin/env node
/**
 * Dev proxy: serves static files + forwards /mcp/* to Arlochat internal ALB.
 * Run: node proxy.js
 * Then open: http://localhost:8082/firmware-regression-assessor.html
 */

const http = require('http');
const fs   = require('fs');
const path = require('path');

const PORT        = parseInt(process.env.PORT) || 8082;
const TARGET_HOST = 'internal-arlochat-mcp-alb-880426873.us-east-1.elb.amazonaws.com';
const TARGET_PORT = 8080;

const MIME = {
  '.html': 'text/html',
  '.js':   'application/javascript',
  '.css':  'text/css',
  '.json': 'application/json',
  '.ico':  'image/x-icon',
};

function cors(res) {
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept');
}

function rewriteEndpoint(data) {
  try {
    const u = new URL(data);
    return `http://localhost:${PORT}/mcp${u.pathname}${u.search}`;
  } catch {
    const p = data.startsWith('/') ? data : '/' + data;
    return `http://localhost:${PORT}/mcp${p}`;
  }
}

function proxySSE(req, res) {
  const targetPath = req.url.replace(/^\/mcp/, '') || '/sse';
  console.log('[proxy] SSE ->', TARGET_HOST + ':' + TARGET_PORT + targetPath);

  const upstream = http.request(
    { host: TARGET_HOST, port: TARGET_PORT, path: targetPath,
      method: 'GET', headers: { Accept: 'text/event-stream' } },
    (upRes) => {
      cors(res);
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      });

      let buf = '', pendingEvent = '';

      upRes.on('data', (chunk) => {
        buf += chunk.toString();
        const lines = buf.split('\n');
        buf = lines.pop(); // keep partial line

        for (const raw of lines) {
          const line = raw.replace(/\r$/, '');

          if (line.startsWith('event:')) {
            pendingEvent = line.slice(6).trim();
            res.write(line + '\n');

          } else if (line.startsWith('data:') && pendingEvent === 'endpoint') {
            const rewritten = rewriteEndpoint(line.slice(5).trim());
            console.log('[proxy] endpoint ->', rewritten);
            res.write('data: ' + rewritten + '\n');
            pendingEvent = '';

          } else {
            res.write(line + '\n');
          }
        }
      });

      upRes.on('end',   ()  => res.end());
      upRes.on('error', (e) => { console.error('[proxy] upstream error:', e.message); res.end(); });
    }
  );

  upstream.on('error', (e) => {
    console.error('[proxy] SSE connect error:', e.message);
    if (!res.headersSent) { cors(res); res.writeHead(502); }
    res.end(e.message);
  });

  upstream.end();
}

function proxyPost(req, res) {
  const targetPath = req.url.replace(/^\/mcp/, '');
  console.log('[proxy] POST ->', TARGET_HOST + ':' + TARGET_PORT + targetPath);

  const chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    const upstream = http.request(
      { host: TARGET_HOST, port: TARGET_PORT, path: targetPath,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': body.length } },
      (upRes) => {
        const parts = [];
        upRes.on('data', (c) => parts.push(c));
        upRes.on('end', () => {
          cors(res);
          res.writeHead(upRes.statusCode);
          res.end(Buffer.concat(parts));
        });
      }
    );
    upstream.on('error', (e) => {
      console.error('[proxy] POST error:', e.message);
      if (!res.headersSent) { cors(res); res.writeHead(502); }
      res.end(e.message);
    });
    upstream.write(body);
    upstream.end();
  });
}

function serveStatic(req, res) {
  let filePath = path.join(__dirname, req.url === '/' ? '/firmware-regression-assessor.html' : req.url);
  fs.readFile(filePath, (err, data) => {
    if (err) { res.writeHead(404); res.end('Not found'); return; }
    const ext  = path.extname(filePath);
    res.writeHead(200, { 'Content-Type': MIME[ext] || 'text/plain' });
    res.end(data);
  });
}

// Pre-warm DNS so first browser request doesn't stall
require('dns').lookup(TARGET_HOST, (err, addr) => {
  if (err) console.warn('[proxy] DNS warmup failed:', err.message);
  else      console.log('[proxy] DNS resolved: ' + TARGET_HOST + ' -> ' + addr);
});

http.createServer((req, res) => {
  if (req.method === 'OPTIONS')             { cors(res); res.writeHead(200); res.end(); return; }
  if (req.url.startsWith('/mcp')) {
    if      (req.method === 'GET')  proxySSE(req, res);
    else if (req.method === 'POST') proxyPost(req, res);
    else                            { res.writeHead(405); res.end(); }
  } else {
    serveStatic(req, res);
  }
}).listen(PORT, () => {
  console.log('Proxy running: http://localhost:' + PORT + '/firmware-regression-assessor.html');
  console.log('Forwarding /mcp/* to http://' + TARGET_HOST + ':' + TARGET_PORT);
  console.log('Press Ctrl+C to stop.');
});
