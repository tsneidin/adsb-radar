#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import os

PROXY_TARGET = 'https://opendata.adsb.fi'
WX_HOST = 'www.aviationweather.gov'

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/v3/'):
            target = PROXY_TARGET + self.path.split('?')[0]
            qs = self.path.split('?', 1)[1] if '?' in self.path else ''
            if qs:
                target += '?' + qs
            req = Request(target, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            })
            try:
                with urlopen(req, timeout=15) as resp:
                    data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Proxy error: {e}'.encode())
            return
        if self.path.startswith('/api/data/'):
            target = 'https://' + WX_HOST + self.path
            try:
                with urlopen(target, timeout=10) as resp:
                    data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Wx proxy error: {e}'.encode())
            return
        super().do_GET()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('', port), Handler)
    print(f'Serving at http://localhost:{port}')
    server.serve_forever()
