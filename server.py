#!/usr/bin/env python3
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import os, json, time

try:
    import requests
except ImportError:
    requests = None

PROXY_TARGET = 'https://opendata.adsb.fi'
WX_HOST = 'www.aviationweather.gov'

# LiveATC feed cache: icao -> (timestamp, feeds_json)
_liveatc_cache = {}

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
        global _liveatc_cache
        now = time.time()
        # Cache for 1 hour
        if icao in _liveatc_cache and now - _liveatc_cache[icao][0] < 3600:
            self.send_json(_liveatc_cache[icao][1])
            return
        
        if not requests:
            self.send_json({'feeds': []})
            return
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        headers = {'User-Agent': ua}
        import re
        
        def parse_pls(text):
            result = []
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
                    result.append({'label': name, 'streamId': sid})
            return result
        
        all_feeds = []
        seen = set()
        
        # Try direct PLS patterns first
        for mount in [icao, f'{icao}_twr', f'{icao}_app', f'{icao}_gnd', f'{icao}_dep',
                      f'{icao}_1', f'{icao}_2', f'{icao}_3', f'{icao}_4',
                      f'{icao}1_twr', f'{icao}1_gnd', f'{icao}1_app', f'{icao}1_atis',
                      f'{icao}1_gnd_twr', f'{icao}_gnd_twr']:
            try:
                pr = requests.get(f'https://www.liveatc.net/play/{mount}.pls',
                                  headers=headers, timeout=5)
                if pr.status_code == 200 and 'File1=' in pr.text:
                    for f in parse_pls(pr.text):
                        if f['streamId'] not in seen:
                            seen.add(f['streamId'])
                            all_feeds.append(f)
            except Exception:
                pass
        
        # If PLS patterns found nothing useful, try search page
        if len(all_feeds) <= 1:
            try:
                r = requests.get(f'https://www.liveatc.net/search/?icao={icao}',
                                 headers=headers, timeout=10)
                if r.status_code == 200:
                    mounts = re.findall(r'play/([a-z0-9_]+)\.pls', r.text)
                    for mount in mounts:
                        if mount not in seen:
                            seen.add(mount)
                            try:
                                pr = requests.get(f'https://www.liveatc.net/play/{mount}.pls',
                                                  headers=headers, timeout=5)
                                if pr.status_code == 200 and 'File1=' in pr.text:
                                    for line in pr.text.split('\n'):
                                        line = line.strip()
                                        if line.startswith('Title'):
                                            parts = line.split('=', 1)
                                            if len(parts) == 2:
                                                all_feeds.append({'label': parts[1].strip(), 'streamId': mount})
                                                break
                            except Exception:
                                pass
            except Exception:
                pass
        
        result = {'feeds': all_feeds}
        _liveatc_cache[icao] = (now, result)
        self.send_json(result)

if __name__ == '__main__':
    # Change to the directory containing this script so radar.html is served
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get('PORT', 8080))
    server = HTTPServer(('', port), Handler)
    print(f'Serving at http://localhost:{port}')
    server.serve_forever()
