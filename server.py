#!/usr/bin/env python3
"""Loopback-only local server. Python 3.11+, no third-party packages."""
import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from core import History, LinuxCollector, demo_frame, investigate, report, SCENARIOS

WEB = Path(__file__).parent / 'web'


class Mission:
    def __init__(self, database, mode='demo'):
        self.history = History(database)
        self.mode = mode
        self.scenario = 'nominal'
        self.tick = 0
        self.lock = threading.Lock()
        self.collector = LinuxCollector()
        self.token = secrets.token_urlsafe(32)
        self.closed = threading.Event()
        self.history.event('startup', f'Session started in {mode} mode')
        self.sample()

    def sample(self):
        with self.lock:
            frame = demo_frame(self.tick, self.scenario) if self.mode == 'demo' else self.collector.sample()
            self.tick += 1
            return self.history.save(frame)

    def run(self):
        while not self.closed.wait(2):
            self.sample()

    def change(self, scenario):
        if self.mode != 'demo':
            raise ValueError('Chaos is available only in demo mode')
        if scenario not in SCENARIOS:
            raise ValueError('Unknown scenario')
        with self.lock:
            self.scenario = scenario
            frame = self.history.save(demo_frame(self.tick, scenario))
            self.tick += 1
            self.history.event('recovery' if scenario == 'nominal' else 'simulation', SCENARIOS[scenario], frame['id'])
        return frame


def make_server(mission, port=8787):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json', download=False):
            if not isinstance(body, bytes): body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            if download: self.send_header('Content-Disposition', 'attachment; filename="yeet-incident.md"')
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.valid_host(): return self.send(403, {'error': 'Local Host header required'})
            url = urlsplit(self.path)
            if url.path == '/api/state':
                with mission.lock:
                    frames = mission.history.frames()
                    events = mission.history.events()
                return self.send(200, {'mode': mission.mode, 'token': mission.token, 'frames': frames,
                                       'events': events, 'findings': investigate(frames[-1]), 'scenarios': SCENARIOS})
            if url.path == '/api/report':
                frames = mission.history.frames()
                try:
                    frame_id = int(parse_qs(url.query).get('frame', [frames[-1]['id']])[0])
                    frame = next(f for f in frames if f['id'] == frame_id)
                except (ValueError, StopIteration):
                    return self.send(404, {'error': 'Frame no longer retained'})
                return self.send(200, report(frame, mission.history.events()).encode(), 'text/markdown; charset=utf-8', True)
            static = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
            if url.path in static:
                filename, mime = static[url.path]
                return self.send(200, (WEB / filename).read_bytes(), mime + '; charset=utf-8')
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if not self.valid_host(): return self.send(403, {'error': 'Local Host header required'})
            allowed_origins = (f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}')
            if self.headers.get('Origin') not in allowed_origins or not secrets.compare_digest(self.headers.get('X-Mission-Token', ''), mission.token):
                return self.send(403, {'error': 'Session token and local Origin required'})
            if self.path != '/api/scenario': return self.send(404, {'error': 'Not found'})
            if self.headers.get('Content-Type') != 'application/json': return self.send(415, {'error': 'JSON required'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024: raise ValueError('Invalid body size')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict): raise ValueError('Expected JSON object')
                frame = mission.change(payload.get('scenario'))
                self.send(200, frame)
            except (ValueError, TypeError):
                self.send(400, {'error': 'Invalid scenario or request body; demo mode required'})

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *_): pass

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['demo', 'host'], default='demo')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--data', type=Path, default=Path('data'))
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Separate histories prevent simulated data being confused with real measurements.
    mission = Mission(args.data / (args.mode + '.sqlite3'), args.mode)
    server = make_server(mission, args.port)
    worker = threading.Thread(target=mission.run, daemon=True); worker.start()
    print(f'YEET Control Room [{args.mode}] → http://127.0.0.1:{server.server_port}', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        mission.closed.set(); server.server_close(); worker.join(timeout=3)


if __name__ == '__main__': main()
