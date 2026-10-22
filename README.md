# YEET Control Room ↗

![yeet-control-room project banner](docs/project-banner.webp)

**Your Linux infrastructure, reimagined as a mission control deck.**

A local-first observability and incident simulation app: live telemetry cards, a service dependency constellation, a flight recorder, historical replay, failure simulations, and downloadable Markdown incident reports.

Built as an AI-assisted learning and portfolio project for Jason Edwards. It has not been deployed on his home server or used by an employer.

## Launch in 10 seconds

Requires Python **3.11+**. No pip, npm, API key, cloud account, Docker socket, or administrator access is needed.

```bash
python3 server.py
```

Open **http://127.0.0.1:8787**. The default mode is a fictional demo universe. Telemetry is generated every two seconds, not on browser requests.

1. Click **Database outage**. The database goes down and its fictional dependents degrade.
2. Click **Restore nominal** to recover the simulated services.
3. Drag the flight recorder slider to revisit a retained frame. Replay stays anchored to that frame as new samples arrive.
4. Click **Export report** to download the selected frame's metrics, observations, and preceding recorded scenario events.
5. Try CPU saturation or disk pressure. Only one scenario is active at a time.

The UI includes a responsive dark flight deck, CPU history bars, UTC timestamps, status colors, textual health indicators, and keyboard-accessible controls. The two-column service cards show arrows to named dependencies; they are a fixed demo topology, not automated host discovery.

## Real Linux telemetry

```bash
python3 server.py --mode host
```

Host mode reads CPU counters, available memory, aggregate received network bytes excluding loopback, and disk usage for `/`. It reads `/proc` and filesystem statistics only. It runs no shell commands, sends no network probes, and cannot restart or stop services. CPU and network rates display unavailable until two samples exist; inaccessible counters remain unavailable rather than showing fabricated data.

**Host mode has no container or systemd service discovery.** The topology is empty and chaos controls are rejected on the server. In a container, host metrics can instead describe the container's visible environment, so run directly on Linux for the intended behavior. CPU percentages reflect `/proc/stat` counters, not container quotas or per-core scheduling. Network receive rates sum interfaces and can double-count traffic on virtual links; they are not an internet bandwidth meter.

Demo and host histories use separate SQLite files so fictional readings do not appear as host evidence.

## Local data and access

- Binds only to IPv4 loopback. Default port: 8787; select another with `--port 8790`.
- Default storage: `data/demo.sqlite3` or `data/host.sqlite3`, relative to your working directory. Use `--data /path/to/private-folder` for another workspace.
- Retains the latest **720 frames** (about 24 minutes at two-second sampling) and **1000 scenario/startup events**. The event API returns the newest 100. Old samples expire; replay advances to the oldest remaining sample if its frame expires.
- The background sampler runs while the server runs. This is not an always-on system agent; restarting starts a nominal demo session while retaining earlier samples.
- Reports reflect only retained frames and available events through the selected frame. They are not a complete audit trail. No raw logs, credentials, filenames, or service command lines are collected.
- Browser requests must use a local Host header. Scenario writes require the startup session token, local Origin, JSON content type, and a body up to 1 KiB. These reduce cross-site request risks; they do not authenticate other programs or users on the computer. No login, TLS, multi-user support, or public deployment is provided.
- For a remote Linux server use an SSH tunnel: `ssh -L 8787:127.0.0.1:8787 user@server`, then open the local URL. Choose a different port if already occupied. Do not expose this server publicly.

## Incident detective

The detective uses explicit rules: a down demo database explains a known dependency impact, and CPU/memory/disk readings at or above 90% trigger investigation suggestions. It does not read logs, discover changes, use an LLM, or establish root cause. Scenario changes are recorded events; they are not discoveries of actual infrastructure failures. The report and UI label these limits.

## Project structure

| File | Responsibility |
| --- | --- |
| `core.py` | Demo generator, Linux collector, bounded SQLite history, incident rules, report text |
| `server.py` | Local HTTP API, sampling thread, session guards, static asset allowlist |
| `web/` | Dependency cards, charts, replay, incident UI, responsive styles |
| `tests/test_mission.py` | Real local HTTP lifecycle, history, fixture collector, rejection paths |
| `.github/workflows/checks.yml` | Python tests, JavaScript and shell syntax checks |

The backend uses Python's standard library HTTP server rather than FastAPI to keep setup dependency-free. This development server is intended for a personal local lab.

## Verify

```bash
python3 -m unittest discover -s tests -v
node --check web/app.js
bash -n publish.sh
```

Nine automated tests cover dependency degradation/recovery, thresholds, persistence, retention, report replay boundaries, real counter parsing with fixture files, unavailable telemetry, the local HTTP lifecycle, session/Origin/Host guards, invalid bodies, unknown frames, forbidden paths, and host-mode chaos rejection. Node is optional and only needed for the JavaScript syntax check. GitHub Actions is supplied; an included workflow is not proof of a successful hosted CI run.

## Publish to GitHub

Unzip the project and, with GitHub CLI authenticated as `cuzzaintit321`, run:

```bash
cd yeet-control-room
bash publish.sh
```

This creates **public** repository `cuzzaintit321/yeet-control-room` and pushes the source, documentation, tests, and workflow. It checks the signed-in account and stages an explicit source allowlist; telemetry databases and runtime folders are excluded. It stops if the folder already has Git history. If the remote name already exists or publication partly succeeds, inspect the local checkout and repository before retrying; the script does not overwrite an existing repository or force-push.

No software license has been selected on your behalf.

### Verification in the preparation environment

Python tests and JavaScript/shell syntax checks passed. The server was started locally and its HTTP routes were exercised by the tests. Visual browser verification could not run because a browser executable was unavailable and the attempted browser download failed. Responsive layout and browser interaction still need a manual check after launch. No successful browser or hosted CI run is claimed.
