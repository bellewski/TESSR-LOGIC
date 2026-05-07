# TESSR-LOGIC

**Multi-Agent Local Build Factory** — shape ideas into buildable projects using a local Ollama LLM pipeline.

---

## What it does

TESSR-LOGIC turns a written requirement into a set of generated source files through a 4-phase AI pipeline:

| Phase | Agent | What it does |
|---|---|---|
| 1 | **Architect** | Reads requirement + project context → produces `structured_spec.md` + `file_plan.json` |
| 2 | **Coder** | Generates every file in the file plan |
| 3 | **Hardener** | Heuristic + LLM security scan, appends remediation notes |
| 4 | **Validator** | Checks completeness and quality; triggers one retry if needed |

Everything runs locally. No cloud. No auth.

---

## New in v0.2 — Living Ecosystem

### Prompt Studio (`/prompt-studio`)
- **Chat panel** — a chatbot that asks focused questions to extract structured requirements
- **Structured form** — platform, features, tech stack, constraints, security sensitivity, etc.
- **Prompt generator** — merges form fields + project context → final build prompt
- **Agent handoff previews** — see what each agent will receive before launching
- **Template save/load** — persist and reuse refined prompts

### Project Context (`/project-context`)
- Create named project contexts with source, workspace, and output directory paths
- **Folder scanner** — recursively scans source dir, ignores `node_modules`, `.git`, `venv`, etc.
- Detects tech stack (Node.js, Python, TypeScript, Docker, Go, Rust, …)
- Lists key files (`package.json`, `pyproject.toml`, `Dockerfile`, …)
- Stores full file manifest in SQLite
- Context summary is injected into the Architect agent prompt automatically

### Build Pipeline (`/pipeline`)
- Live table of all builds with phase timeline indicators
- Auto-refreshes every 5 s while builds are active
- Filter by status: running / queued / completed / failed

### Artifacts (`/artifacts`)
- Browse completed builds with their final output paths
- Shows source, workspace, and output directories per build
- File count written to output directory

### Context-aware builds
- On build creation, link a **ProjectContext** and the Architect sees it
- Generated files are copied to the configured **output directory** on completion
- `BuildDirectoryConfig` records final output path and file count in DB

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + SQLAlchemy + SQLite |
| LLM | Ollama (local, HTTP) |
| Frontend | React + Vite + TypeScript + Tailwind CSS |
| Transport | REST API + WebSocket (real-time events) |

---

## Quick start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.ai) running locally with at least one model pulled (e.g. `ollama pull llama3`)

### Backend

```bash
# From repo root
pip install -r requirements.txt

# Optional: copy and edit environment config
cp .env.example .env

# Start the API server
uvicorn backend.main:app --reload --port 8000
```

API available at `http://localhost:8000`. Swagger docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI available at `http://localhost:5173`.

---

## API highlights

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/builds` | Create + enqueue a build (accepts `project_context_id`, `source_dir`, etc.) |
| `GET` | `/api/builds/{id}/directories` | Get directory config + final output path for a build |
| `POST` | `/api/contexts` | Create a project context |
| `POST` | `/api/contexts/{id}/scan` | Scan a source directory and store results |
| `GET` | `/api/contexts/{id}/manifest` | List all scanned files for a context |
| `POST` | `/api/contexts/scan` | Quick scan (creates context + scans in one call) |
| `GET` | `/api/prompts/templates` | List saved prompt templates |
| `POST` | `/api/prompts/templates` | Save a prompt template |
| `POST` | `/api/prompts/chat` | Chat with the requirement-refining bot |
| `POST` | `/api/prompts/generate` | Generate final build prompt from structured fields |
| `WS` | `/ws/builds/{id}` | Real-time build event stream |

---

## Project structure

```
TESSR-LOGIC/
├── backend/
│   ├── agents/          # Architect, Coder, Hardener, Validator
│   ├── api/routes/      # builds, context, prompts, settings, ollama, files
│   ├── models/          # SQLAlchemy ORM models
│   ├── orchestrator/    # Pipeline, job queue, event bus
│   ├── providers/       # Ollama HTTP provider
│   ├── repositories/    # DB access layer
│   ├── schemas/         # Pydantic request/response models
│   ├── services/        # build_service, scanner_service, prompt_service
│   └── main.py
├── frontend/
│   └── src/
│       ├── api/         # builds, context, prompts, settings clients
│       ├── components/  # Sidebar, TopBar, EventLog, FilesViewer, etc.
│       ├── hooks/       # useBuilds, useBuildEvents
│       ├── pages/       # Dashboard, PromptStudio, ProjectContext,
│       │                #   BuildPipeline, Artifacts, BuildDetail, Settings
│       └── types/       # TypeScript interfaces
├── workspace/builds/    # Default build artifact storage
├── requirements.txt
├── .env.example
└── README.md
```

---

## Ignored folders (scanner)

`node_modules` · `.git` · `venv` · `.venv` · `dist` · `build` · `__pycache__` · `coverage` · `.next` · `.nuxt` · `.svelte-kit` · `target` · `out`

---

## Licence

MIT
