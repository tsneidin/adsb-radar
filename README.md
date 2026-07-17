# ADS-B Radar Scope

Browser-based ATC radar scope that displays live aircraft positions from ADS-B data.

## Quick Start

```bash
python3 server.py
```

Open **http://localhost:8080/radar.html** in your browser.

## How It Works

The Python server (`server.py`) serves the web page and proxies requests to the [opendata.adsb.fi](https://opendata.adsb.fi) API, bypassing CORS restrictions. The browser renders a rotating radar sweep with aircraft blips, trails, callsign labels, and a target list sidebar.

- Polls for new data every 3 seconds
- Radar sweep rotates at configurable 5–20 RPM
- Click any target to see detailed information
- Change center airport via ICAO code search
- Range buttons: 10, 25, 50 NM

## Files

| File | Purpose |
|------|---------|
| `server.py` | HTTP server + API proxy |
| `radar.html` | Full scope UI (single-file, no dependencies) |

## Data Source

Uses the free [adsb.fi Open Data API](https://github.com/adsbfi/opendata) — no API key required.
