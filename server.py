import http.server
import urllib.request
import urllib.error
import json
import os
import sys

ADSB_API = 'https://adsb.lol'
LIVEATC_API = 'https://www.liveatc.net'
PORT = int(os.environ.get('PORT', 8080))


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/v3/'):
            self.proxy(ADSB_API + self.path)
        elif self.path.startswith('/api/liveatc/'):
            icao = self.path.split('/')[-1]
            url = f'{LIVEATC_API}/ajax/get_audio.php?icao={icao}'
            self.proxy(url, is_liveatc=True)
        else:
            super().do_GET()

    def proxy(self, url, is_liveatc=False):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header('Access-Control-Allow-Origin', '*')
                if is_liveatc:
                    self.send_header('Content-Type', 'application/json')
                else:
                    ct = resp.headers.get('Content-Type', 'application/json')
                    self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())
        except Exception as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def log_message(self, fmt, *args):
        sys.stderr.write(f'[server] {args[0]} {args[1]} {args[2]}\n')


if __name__ == '__main__':
    httpd = http.server.HTTPServer(('0.0.0.0', PORT), ProxyHandler)
    print(f'ADS-B Radar server on port {PORT}')
    httpd.serve_forever()
