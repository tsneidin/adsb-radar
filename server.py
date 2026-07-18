#!/usr/bin/env python3
from http.server import HTTPServer, ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
import os, json, time, re

PROXY_TARGET = 'https://opendata.adsb.fi'
WX_HOST = 'www.aviationweather.gov'

# LiveATC feed cache: icao -> (timestamp, feeds_json)
_liveatc_cache = {}
_last_search_time = 0
_airport_cache = None  # (timestamp, list)

def load_airport_data():
    global _airport_cache
    now = time.time()
    if _airport_cache and now - _airport_cache[0] < 3600:
        return _airport_cache[1]
    try:
        import gzip
        req = Request(
            'https://cdn.jsdelivr.net/npm/@squawk/airport-data@0.7.10/data/airports.json.gz',
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urlopen(req, timeout=15) as resp:
            raw = gzip.decompress(resp.read())
        data = json.loads(raw)
        result = []
        for r in data.get('records', []):
            if r.get('country') != 'US': continue
            if r.get('facilityType') != 'AIRPORT' or r.get('ownershipType') != 'PUBLIC': continue
            if r.get('status') != 'OPEN': continue
            if not r.get('fuelTypes'): continue
            if not r.get('icao'): continue
            result.append({
                'icao': r['icao'], 'faaId': r.get('faaId',''),
                'lat': r['lat'], 'lon': r['lon'],
                'name': r.get('name',''), 'state': r.get('state',''),
                'timezone': r.get('timezone',''),
                'r': r.get('runways',[]), 'wxId': r['icao'],
            })
        _airport_cache = (now, result)
        return result
    except Exception as e:
        raise e

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/airports':
            try:
                aps = load_airport_data()
                self.send_json(aps)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f'Airport load error: {e}'.encode())
            return
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
        if self.path.startswith('/api/nnum/'):
            nnum = self.path.split('/api/nnum/')[1].split('?')[0].strip().upper()
            if not nnum:
                self.send_json({})
                return
            self.handle_nnum(nnum)
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
        global _liveatc_cache, _last_search_time
        now = time.time()
        # Cache for 1 hour
        if icao in _liveatc_cache and now - _liveatc_cache[icao][0] < 3600:
            self.send_json(_liveatc_cache[icao][1])
            return
        
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        headers = {'User-Agent': ua}
        
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
        
        # Try direct PLS patterns (always works, no rate limiting)
        for mount in [icao, f'{icao}_twr', f'{icao}_app', f'{icao}_gnd', f'{icao}_dep',
                      f'{icao}_1', f'{icao}_2', f'{icao}_3', f'{icao}_4',
                      f'{icao}1_twr', f'{icao}1_gnd', f'{icao}1_app', f'{icao}1_atis',
                      f'{icao}1_gnd_twr', f'{icao}_gnd_twr']:
            try:
                pr = urlopen(Request(f'https://www.liveatc.net/play/{mount}.pls', headers=headers),
                             timeout=5)
                body = pr.read().decode('utf-8')
                if 'File1=' in body:
                    for f in parse_pls(body):
                        if f['streamId'] not in seen:
                            seen.add(f['streamId'])
                            all_feeds.append(f)
            except Exception:
                pass
        
        # Always try search page with rate limiting (more comprehensive)
        if _last_search_time + 2.5 < now:
            _last_search_time = now
            try:
                r = urlopen(Request(f'https://www.liveatc.net/search/?icao={icao}', headers=headers),
                            timeout=10)
                body = r.read().decode('utf-8')
                mounts = re.findall(r'play/([a-z0-9_]+)\.pls', body)
                for mount in mounts:
                    if mount not in seen:
                        seen.add(mount)
                        try:
                            pr = urlopen(Request(f'https://www.liveatc.net/play/{mount}.pls', headers=headers),
                                         timeout=5)
                            pbody = pr.read().decode('utf-8')
                            if 'File1=' in pbody:
                                for line in pbody.split('\n'):
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

    def handle_nnum(self, nnum):
        result = {'nNumber': nnum}
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        try:
            url = f'https://registry.faa.gov/AircraftInquiry/Search/NNumberResult?NNumbertxt={nnum}'
            req = Request(url, headers={'User-Agent': ua})
            with urlopen(req, timeout=3) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            m = re.search(r'<td[^>]*>Name</td>\s*<td[^>]*>([^<]+)</td>', html, re.IGNORECASE)
            if m: result['owner'] = m.group(1).strip()
            m = re.search(r'<td[^>]*>City</td>\s*<td[^>]*>([^<]+)</td>', html, re.IGNORECASE)
            if m: result['city'] = m.group(1).strip()
            m = re.search(r'<td[^>]*>State</td>\s*<td[^>]*>([^<]+)</td>', html, re.IGNORECASE)
            if m: result['state'] = m.group(1).strip()
        except Exception:
            pass
        self.send_json(result)

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get('PORT', 8080))
    server = ThreadingHTTPServer(('', port), Handler)
    server.timeout = 0.5
    print(f'Serving at http://localhost:{port}')
    server.serve_forever()
