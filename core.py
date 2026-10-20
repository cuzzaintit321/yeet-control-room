"""Deterministic mission simulation, SQLite history, and read-only Linux telemetry."""
import json
import math
import shutil
import sqlite3
import time
from pathlib import Path

SERVICES = [
    {'id': 'edge', 'name': 'Nginx gateway', 'kind': 'PROXY', 'depends': ['api']},
    {'id': 'api', 'name': 'Mission API', 'kind': 'APPLICATION', 'depends': ['db']},
    {'id': 'db', 'name': 'PostgreSQL', 'kind': 'DATABASE', 'depends': []},
    {'id': 'archive', 'name': 'Archive worker', 'kind': 'BACKUP', 'depends': ['db']},
]
SCENARIOS = {'nominal': 'All systems nominal', 'database': 'Database unavailable',
             'cpu': 'CPU saturation', 'disk': 'Disk pressure'}


def demo_frame(tick, scenario='nominal'):
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    services = []
    for s in SERVICES:
        status = 'healthy'
        reason = 'Responding within expected range'
        if scenario == 'database':
            status = 'down' if s['id'] == 'db' else 'degraded'
            reason = 'Simulated database stop' if s['id'] == 'db' else 'Database dependency unavailable'
        if scenario == 'cpu' and s['id'] in ('api', 'edge'):
            status, reason = 'degraded', 'Simulated CPU contention'
        services.append(dict(s, status=status, reason=reason,
                             latency_ms=round(15 + 8 * (1 + math.sin(tick / 5 + len(s['id'])))
                                              + (230 if status == 'degraded' else 0), 1)))
    return {'mode': 'demo', 'scenario': scenario, 'services': services,
            'metrics': {'cpu_pct': 96 if scenario == 'cpu' else round(24 + 10 * math.sin(tick / 8), 1),
                        'memory_pct': round(43 + 4 * math.sin(tick / 11), 1),
                        'disk_pct': 94 if scenario == 'disk' else 36,
                        'network_rx_kbps': round(120 + 50 * math.sin(tick / 6), 1)},
            'notes': ['Fictional service topology and telemetry. No host services are changed.']}


class LinuxCollector:
    """Reads /proc and disk usage only. Never invokes shell commands or Docker."""
    def __init__(self, proc='/proc', disk_path='/'):
        self.proc = Path(proc)
        self.disk_path = disk_path
        self.previous = None

    def sample(self):
        metrics = dict.fromkeys(['cpu_pct', 'memory_pct', 'disk_pct', 'network_rx_kbps'])
        notes = []
        now = time.monotonic()
        cpu = rx = None
        try:
            fields = (self.proc / 'stat').read_text().splitlines()[0].split()[1:9]
            vals = list(map(int, fields))
            cpu = (sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0))
        except (OSError, ValueError, IndexError):
            notes.append('CPU telemetry unavailable')
        try:
            mem = {k: int(v.strip().split()[0]) for k, v in
                   (line.split(':', 1) for line in (self.proc / 'meminfo').read_text().splitlines())}
            metrics['memory_pct'] = round(100 * (1 - mem['MemAvailable'] / mem['MemTotal']), 1)
        except (OSError, ValueError, KeyError, ZeroDivisionError):
            notes.append('Memory telemetry unavailable')
        try:
            usage = shutil.disk_usage(self.disk_path)
            metrics['disk_pct'] = round(100 * usage.used / usage.total, 1)
        except (OSError, ZeroDivisionError):
            notes.append('Disk telemetry unavailable')
        try:
            rx = sum(int(line.split(':', 1)[1].split()[0])
                     for line in (self.proc / 'net/dev').read_text().splitlines()[2:]
                     if ':' in line and line.split(':')[0].strip() != 'lo')
        except (OSError, ValueError, IndexError):
            notes.append('Network telemetry unavailable')
        if self.previous:
            prev_time, prev_cpu, prev_rx = self.previous
            if cpu and prev_cpu and cpu[0] > prev_cpu[0]:
                metrics['cpu_pct'] = round(max(0, min(100, 100 * (1 - (cpu[1] - prev_cpu[1]) / (cpu[0] - prev_cpu[0])))), 1)
            if rx is not None and prev_rx is not None and rx >= prev_rx and now > prev_time:
                metrics['network_rx_kbps'] = round((rx - prev_rx) / (now - prev_time) / 1024, 1)
        else:
            notes.append('CPU and network rates need two samples')
        self.previous = now, cpu, rx
        return {'mode': 'host', 'scenario': 'read-only', 'services': [], 'metrics': metrics,
                'notes': notes + ['Local host metrics only. Docker and systemd service discovery are not enabled.']}


class History:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY, ts REAL NOT NULL, payload TEXT NOT NULL);'
                             'CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, frame_id INTEGER);')

    def connect(self):
        return sqlite3.connect(self.path)

    def save(self, frame):
        frame = dict(frame, ts=time.time())
        with self.connect() as db:
            cur = db.execute('INSERT INTO frames(ts,payload) VALUES (?,?)', (frame['ts'], json.dumps(frame)))
            frame['id'] = cur.lastrowid
            # Bound disk growth: last 720 samples and 1000 events, not an archival store.
            db.execute('DELETE FROM frames WHERE id <= (SELECT COALESCE(MAX(id),0)-720 FROM frames)')
        return frame

    def frames(self):
        with self.connect() as db:
            return [dict(json.loads(payload), id=i) for i, payload in db.execute('SELECT id,payload FROM frames ORDER BY id')]

    def event(self, kind, message, frame_id=None):
        with self.connect() as db:
            db.execute('INSERT INTO events(ts,kind,message,frame_id) VALUES (?,?,?,?)', (time.time(), kind, message, frame_id))
            db.execute('DELETE FROM events WHERE id <= (SELECT COALESCE(MAX(id),0)-1000 FROM events)')

    def events(self):
        with self.connect() as db:
            return [dict(id=i, ts=t, kind=k, message=m, frame_id=f) for i,t,k,m,f in
                    db.execute('SELECT id,ts,kind,message,frame_id FROM events ORDER BY id DESC LIMIT 100')]


def investigate(frame):
    """Evidence-based rules; correlations are observations, not inferred root causes."""
    findings = []
    if any(s['id'] == 'db' and s['status'] == 'down' for s in frame['services']):
        findings.append('Database is down; API, gateway, and archive depend on it in the demo topology. Check database availability before downstream services.')
    for key, threshold, message in [
        ('cpu_pct', 90, 'CPU exceeds 90%. Review workload and per-process usage.'),
        ('disk_pct', 90, 'Disk exceeds 90%. Review capacity and retention before deleting anything.'),
        ('memory_pct', 90, 'Memory exceeds 90%. Inspect process usage and memory pressure.')]:
        val = frame['metrics'].get(key)
        if val is not None and val >= threshold:
            findings.append(message)
    return findings or ['No configured threshold or dependency rule is triggered in this frame.']


def report(frame, events):
    from datetime import datetime, timezone
    stamp = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat()
    lines = ['# YEET Control Room — Incident report', '', f"Mode: {frame['mode']}",
             f"Frame: {frame['id']} / {stamp(frame['ts'])}", f"Scenario: {frame['scenario']}", '', '## Metrics']
    lines += [f'- {k}: {v if v is not None else "unavailable"}' for k,v in frame['metrics'].items()]
    lines += ['', '## Observations (rule-based; not proof of root cause)'] + ['- ' + x for x in investigate(frame)]
    lines += ['', '## Recorded events through selected frame']
    lines += [f"- {stamp(e['ts'])}: {e['message']}" for e in reversed(events)
              if e['frame_id'] is not None and e['frame_id'] <= frame['id']]
    lines += ['', '## Scope', 'Demo events are simulated. Host mode reads only local /proc and disk usage.',
              'History is bounded. This report is an aid to investigation, not a complete audit log.']
    return '\n'.join(lines) + '\n'
