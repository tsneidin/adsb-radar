#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import os, json

try:
    import requests
except ImportError:
    requests = None

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
        if self.path.startswith('/api/liveatc/'):
            icao = self.path.split('/api/liveatc/')[1].split('?')[0].strip().lower()
            if not icao:
                self.send_json({'feeds': []})
                return
            self.handle_liveatc(icao)
            return
        super().do_GET()

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def handle_liveatc(self, icao):
        if not requests:
            self.send_json({'feeds': []})
            return
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        def parse_pls(text):
            feeds = []
            files, titles = {}, {}
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('File'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        idx = parts[0].replace('File', '')
                        files[idx] = parts[1].strip()
                elif line.startswith('Title'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        idx = parts[0].replace('Title', '')
                        titles[idx] = parts[1].strip()
            for idx in sorted(files):
                url_val = files[idx]
                name = titles.get(idx, '')
                sid = url_val.rsplit('/', 1)[-1].split('?')[0]
                if sid:
                    feeds.append({'label': name, 'streamId': sid})
            return feeds
        
        def try_pls(mount):
            try:
                r = requests.get(f'https://www.liveatc.net/play/{mount}.pls',
                                 headers={'User-Agent': ua}, timeout=8)
                if r.status_code == 200 and 'File1=' in r.text:
                    return parse_pls(r.text)
            except Exception:
                pass
            return []
        
        seen = set()
        all_feeds = []
        # Try the bare ICAO code first
        candidates = [icao, f'{icao}_twr', f'{icao}_app', f'{icao}_gnd', f'{icao}_dep']
        for mount in candidates:
            for f in try_pls(mount):
                if f['streamId'] not in seen:
                    seen.add(f['streamId'])
                    all_feeds.append(f)
        self.send_json({'feeds': all_feeds})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('', port), Handler)
    print(f'Serving at http://localhost:{port}')
    server.serve_forever()
