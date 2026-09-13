<div align="center">

# Soulforge

**A cross-Agent system-prompt file manager for OpenClaw with a Web GUI**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](backend/pyproject.toml)
[![Backend](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](backend)
[![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB.svg)](frontend)

English · [简体中文](README.zh-CN.md)

</div>

***

## Overview

OpenClaw is a multi-Agent system in which every Agent owns a `workspace/` containing its core "Prompt Pack" files, such as `SOUL.md`, `AGENTS.md`, `USER.md`, `MEMORY.md`, and `TOOLS.md`.

**Soulforge** is the unified management tool for all these files. It treats every Agent's "soul files" as source code that you can browse, search, edit, compare, sync, back up, and package — all from a single Web page.

- **Single-process deployment** — one `uvicorn` process serves both the REST API and the built React frontend.
- **Local-only by default** — listens on `127.0.0.1:8848`, never exposed to the public network.
- **Zero config to start** — `start.bat` detects your OpenClaw root, creates the Python virtual environment, installs dependencies, and launches the app automatically.

## Key Features

| Feature                 | Description                                                                                                                                                     |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Unified editing**     | Open and edit the same-named prompt file across multiple Agents at once; WYSIWYG markdown preview with live editing.                                            |
| **Cross-Agent search**  | Full-text search across every Agent's prompt files (powered by ripgrep), with context lines and jump-to-result.                                                 |
| **Export**              | Package an Agent's prompt pack into `.tar.gz` with a SHA-256 manifest for archiving / migration. |
| **Diff**                | Compare the same file across Agents or against a historical backup (similarity score + unified/HTML diff).                                                      |
| **Cross-Agent sync**    | Generate a sync plan first, then execute only the files you confirm — selective merge, never a whole-file overwrite.                                            |
| **Super Sync**          | Runs as a **standalone process** once enabled (keeps syncing even after the main app exits), keeping same-named core documents across Agents consistent within seconds; UI start/stop, live status, matrix scope selection, and log search / export. |
| **Backup & rollback**   | Automatic backup before every write, retention policy, full history, and one-click rollback.                                                                    |
| **Lint**                | 8 built-in rules, including L4 anti-pattern detection (timestamps, version numbers, narrative) and required-core-file checks.                                   |
| **Stats & audit**       | Dashboard metrics (agents, files, backups, warnings) and a full audit log for every write operation.                                                            |
| **Config center**       | Read and edit `config.toml` from the UI without touching files by hand.                                                                                         |
| **Security guardrails** | Path-traversal protection, SHA-256 optimistic locking, and mandatory backup before any write.                                                                   |
| **Document presets** *(Phase 2.5)*     | Save reusable structure templates for `SOUL.md`, `AGENTS.md`, `MEMORY.md`, work logs, and more; apply them via plan + confirm. |
| **LLM providers** *(Phase 2.5)*        | Plug in any OpenAI-compatible LLM (OpenAI / Anthropic / DeepSeek / Ollama) with encrypted API keys and hot reload.                                                |
| **AI organise** *(Phase 2.5)*          | Run an Agent on a chosen file against a preset, review the diff, then write — keeps every soul file consistently structured.                                       |

## Roadmap

Soulforge ships in phases:

| Phase | Scope | Status |
|---|---|---|
| **Phase 1 · MVP** | Browse + edit + backup + lint + sync + export + dashboard | ✅ Shipped (v0.1 → v1.0) |
| **Phase 2 · UI polish** | Layout refinements, theming, keyboard shortcuts, real-time status bar | 🚧 In progress |
| **Phase 2.5 · AI Editor** | Document presets → LLM provider plug-in → AI-powered document organising (3-step plan) | 🚧 In progress |
| **Super Sync** | Second-level (near real-time) sync of same-named core documents across Agents (standalone daemon + UI matrix scope / status / logs) | ✅ Shipped |
| **Phase 3 · Far future** | Team collaboration / cloud sync / third-party plugins | 📋 Planned |

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

## Tech Stack

| Layer      | Technology                                                                               |
| ---------- | ---------------------------------------------------------------------------------------- |
| Backend    | Python 3.10+, FastAPI, SQLAlchemy, Uvicorn, loguru                                       |
| Frontend   | React 18 + TypeScript + Vite, Monaco Editor, marked / turndown (WYSIWYG preview)         |
| Storage    | SQLite (`index.db`) + ripgrep for full-text search                                       |
| Deployment | Local single process (`start.bat` / uvicorn), serves built frontend from `frontend/dist` |

## Requirements

- **Python 3.10 or newer** (with `pip`)
- **Node.js 18+ and npm** (only needed to build or develop the frontend)
- **An OpenClaw installation** — the app reads `openclaw.json` to discover Agents and their `workspace/` directories

All runtime data lives inside the project directory under `.soulforge/` (database, backups, logs, `config.toml`, plus `super_sync/` for Super Sync), so the project never depends on external global paths.

## Quick Start

### Windows (one-click launcher)

1. Clone this repository to `<OpenClawRoot>\workspace\projects\soulforge` (or set `SOULFORGE_OPENCLAW_DIR` to your OpenClaw root).
2. Double-click `start.bat`. It will:
   - detect the OpenClaw root (or use `SOULFORGE_OPENCLAW_DIR`);
   - create `backend\.venv` and install backend dependencies;
   - launch the server and open `http://127.0.0.1:8848`.

### Manual setup (any platform)

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install "fastapi>=0.110" "uvicorn[standard]>=0.29" "sqlalchemy>=2.0" \
            "pydantic>=2.6" "python-multipart>=0.0.9" "loguru>=0.7" "send2trash>=1.8" tomli
uvicorn main:app --host 127.0.0.1 --port 8848
```

Frontend (build once; the backend serves `frontend/dist`):

```bash
cd frontend
npm install
npm run build
```

Then open <http://127.0.0.1:8848>.

### Frontend development mode

```bash
cd frontend
npm run dev        # Vite dev server, proxies /api to http://127.0.0.1:8848
```

## Configuration

| Environment variable     | Default                     | Purpose                                             |
| ------------------------ | --------------------------- | --------------------------------------------------- |
| `SOULFORGE_DATA_DIR`     | `<project-root>/.soulforge` | Data directory (DB, backups, logs, config, `super_sync/`) |
| `SOULFORGE_OPENCLAW_DIR` | Auto-detected OpenClaw root | Directory that contains `openclaw.json`             |
| `SOULFORGE_PORT`         | `8848`                      | Server port                                         |

Runtime configuration is stored in `.soulforge/config.toml` (server, backup retention, lint rules, UI defaults, advanced options) and can be edited from the **Settings** dialog in the UI.

## API Reference

Base URL: `http://127.0.0.1:8848/api` · Interactive OpenAPI docs: <http://127.0.0.1:8848/docs>

| Method        | Endpoint                                                          | Description                                 |
| ------------- | ----------------------------------------------------------------- | ------------------------------------------- |
| `GET`         | `/api/health`                                                     | Health check                                |
| `GET`         | `/api/agents`                                                     | List all Agents                             |
| `POST`        | `/api/agents/scan`                                                | Rescan all Agent workspaces                 |
| `GET`         | `/api/agents/{id}/files`                                          | List an Agent's prompt-pack files           |
| `GET`         | `/api/agents/{id}/files/{path}`                                   | Read a file                                 |
| `PUT`         | `/api/agents/{id}/files/{path}`                                   | Write a file (auto-backup, optimistic lock) |
| `GET`         | `/api/agents/{id}/files/{path}/history`                           | File backup history                         |
| `POST`        | `/api/search`                                                     | Cross-Agent full-text search                |
| `GET`         | `/api/diff`                                                       | Diff the same file across two Agents        |
| `POST`        | `/api/sync/plan`                                                  | Create a sync plan                          |
| `POST`        | `/api/sync/execute`                                               | Execute a sync plan                         |
| `GET` / `PUT` | `/api/super-sync/config`                                          | Read / update Super Sync scope              |
| `GET`         | `/api/super-sync/status`                                          | Super Sync state (running / stopped / error) |
| `POST`        | `/api/super-sync/start` · `/api/super-sync/stop`                  | Start / stop the standalone sync process    |
| `GET`         | `/api/super-sync/logs` · `/api/super-sync/logs/export`            | Query / export sync logs                    |
| `GET`         | `/api/export/{id}` / `/api/export/all`                            | Export an Agent / all Agents as `.tar.gz`   |
| `GET`         | `/api/backups/{id}`                                               | List an Agent's backups                     |
| `POST`        | `/api/backups/{id}/{path}/rollback`                               | Roll back a file to a backup                |
| `GET`         | `/api/lint/{id}` / `/api/lint/file/{id}/{path}` / `/api/lint/all` | Lint an Agent / a file / all Agents         |
| `GET`         | `/api/stats`                                                      | Dashboard statistics                        |
| `GET`         | `/api/audit`                                                      | Audit log                                   |
| `GET` / `PUT` | `/api/config`                                                     | Read / update configuration                 |

All responses follow the envelope `{"data": ...}`; errors return `{"error": {"code", "message", "details"}}`.
See [docs/API.md](docs/API.md) for the complete specification.

## Project Structure

```
soulforge/
├── backend/                  # FastAPI backend
│   ├── main.py               # App entry
│   ├── super_sync.py         # Super Sync standalone daemon (runs detached from the app)
│   ├── app/
│   │   ├── api/              # Routers (agents, files, search, diff, sync, super-sync, ...)
│   │   ├── services/         # Business services (discovery, backup, lint, super_sync, ...)
│   │   ├── models/           # SQLAlchemy models + Pydantic schemas
│   │   └── core/             # Errors, logging, security
│   ├── tests/                # pytest suite
│   └── pyproject.toml
├── frontend/                 # React + Vite frontend
│   ├── src/                  # Components, hooks, api client, styles
│   ├── dist/                 # Build output (served by the backend)
│   └── package.json
├── docs/                     # Detailed docs (architecture, API, data model, ...)
├── .github/                  # Issue & PR templates
├── README.md                 # This file
└── LICENSE                   # MIT license
```

## Documentation

| Document                                     | Content                                                               |
| -------------------------------------------- | --------------------------------------------------------------------- |
| [DEVELOPMENT.md](DEVELOPMENT.md)             | Main development guide (goals / architecture / features / data model) |
| [docs/API.md](docs/API.md)                   | Complete REST API specification                                       |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture                                                   |
| [docs/DATA-MODEL.md](docs/DATA-MODEL.md)     | Data model (SQLite schema, file metadata)                             |
| [docs/SECURITY.md](docs/SECURITY.md)         | Security guardrails                                                   |
| [docs/ROADMAP.md](docs/ROADMAP.md)           | Roadmap (MVP / v1.0 / v1.x)                                           |
| [UI-SPECS.md](UI-SPECS.md)                   | UI design specification                                               |

## Contributing

Contributions are welcome! Please follow the workflow below:

1. **Fork** the repository and create a feature branch: `git checkout -b feat/my-feature`
2. **Write code** — keep changes focused and consistent with the existing style:
   - Backend: follow [DEVELOPMENT.md](DEVELOPMENT.md), run `ruff check` and add/extend tests with `pytest` (run from `backend/`).
   - Frontend: run `npm run build` (includes `tsc --noEmit`) before submitting.
3. **Commit** with a clear message describing *why* the change is needed.
4. **Open a pull request** — use the [PR template](.github/PULL_REQUEST_TEMPLATE.md) and make sure all CI checks pass.

Guidelines:

- Never write metadata into Agent workspaces; Soulforge data stays in `.soulforge/`.
- Never overwrite a whole file during cross-Agent sync — always selective merge.
- All write operations must go through the backup + audit pipeline.

## License

Distributed under the [MIT License](LICENSE).

## Contact

- Maintainer: **RuanCH0924**
- For bugs, feature requests, or questions, please open an issue in the [GitHub Issues](https://github.com/RuanCH0924/soulforge/issues) tracker.

