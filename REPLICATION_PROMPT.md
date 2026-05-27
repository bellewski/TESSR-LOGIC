# TESSR-LOGIC Build Guide

Use this guide to build your own TESSR-LOGIC multi-agent local build factory application from scratch.

## Overview

TESSR-LOGIC is a **Multi-Agent Local Build Factory** that turns written requirements into generated source files through a 4-phase AI pipeline running entirely locally using Ollama.

**What you'll build**: A complete web application with FastAPI backend, React frontend, and AI-powered code generation pipeline.

## System Architecture

### Core Components
- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: React + Vite + TypeScript + Tailwind CSS  
- **LLM Engine**: Ollama (local, HTTP)
- **Transport**: REST API + WebSocket (real-time events)

### 4-Phase AI Pipeline
1. **Architect** - Reads requirements + project context → produces `structured_spec.md` + `file_plan.json`
2. **Coder** - Generates every file in the file plan
3. **Hardener** - Heuristic + LLM security scan, appends remediation notes
4. **Validator** - Checks completeness and quality; triggers one retry if needed

### Key Features
- **Prompt Studio** - Chat panel + structured form + prompt generator + agent handoff previews
- **Project Context** - Folder scanner + tech stack detection + file manifest storage
- **Build Pipeline** - Live build table with phase timeline indicators
- **Artifacts Browser** - Browse completed builds with output paths

## Prerequisites

### Required Software
- **Python 3.11+**
- **Node.js 18+**
- **Ollama** running locally (https://ollama.ai)
- **Windsurf IDE** - Recommended IDE for development (has built-in AI assistant)

### Ollama Setup
```bash
# Install Ollama first, then pull models
ollama pull qwen2.5-coder:7b     # Fast/draft builds
ollama pull qwen2.5-coder:14b    # Quality builds (optional)
```

## Build Steps

### 1. Project Setup
```bash
# Create your TESSR-LOGIC project directory
mkdir TESSR-LOGIC
cd TESSR-LOGIC

# Initialize git (optional)
git init
```

### 2. Backend Setup
Create `requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
sqlalchemy>=2.0.30
pydantic>=2.11.0
pydantic-settings>=2.7.0
httpx>=0.27.0
python-multipart>=0.0.9
aiofiles>=23.2.1
```

Create `.env.example`:
```env
# TESSR-LOGIC Environment Configuration
# Copy this file to .env and adjust values as needed.

# ── Ollama ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_FAST_MODEL=llama3.2:3b
OLLAMA_QUALITY_MODEL=codellama:13b
OLLAMA_TIMEOUT=300

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite:///./tessr_logic.db

# ── Workspace ────────────────────────────────────────────────────────────────
WORKSPACE_PATH=./workspace/builds

# ── App ───────────────────────────────────────────────────────────────────────
APP_NAME=TESSR-LOGIC
DEBUG=false
```

### 3. Backend Structure
Create the following directory structure:
```
backend/
├── agents/          # Architect, Coder, Hardener, Validator agents
├── api/routes/      # API endpoints (builds, context, prompts, settings, ollama, files)
├── models/          # SQLAlchemy ORM models
├── orchestrator/    # Pipeline, job queue, event bus
├── providers/       # Ollama HTTP provider
├── repositories/    # Database access layer
├── schemas/         # Pydantic request/response models
├── services/        # build_service, scanner_service, prompt_service
├── core/            # Core archetype and configurations
└── main.py          # FastAPI application entry point
```

### 4. Frontend Setup
Create `frontend/package.json`:
```json
{
  "name": "tessr-logic-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "axios": "^1.7.7",
    "lucide-react": "^0.441.0",
    "clsx": "^2.1.1",
    "date-fns": "^3.6.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.4.8",
    "tailwindcss": "^3.4.12",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47"
  }
}
```

### 5. Frontend Structure
Create the following directory structure:
```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── api/         # API clients (builds, context, prompts, settings)
│   ├── components/  # UI components (Sidebar, TopBar, EventLog, FilesViewer, etc.)
│   ├── hooks/       # React hooks (useBuilds, useBuildEvents)
│   ├── pages/       # Page components (Dashboard, PromptStudio, ProjectContext, BuildPipeline, Artifacts, BuildDetail, Settings)
│   ├── types/       # TypeScript interfaces
│   ├── App.tsx      # Main app component
│   ├── main.tsx     # Entry point
│   └── index.css    # Global styles
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
└── postcss.config.js
```

### 6. Installation & Startup
```bash
# Backend setup
pip install -r requirements.txt
cp .env.example .env  # Edit .env as needed

# Frontend setup
cd frontend
npm install
cd ..

# Create workspace directory
mkdir -p workspace/builds

# Start services (in separate terminals)
# Terminal 1: Backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend  
cd frontend
npm run dev
```

### 7. Access Points
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Frontend UI**: http://localhost:5173

## Key Implementation Notes

### Database Models Needed
- Build (with phases: architect, coder, hardener, validator)
- ProjectContext (source/workspace/output directories)
- PromptTemplate
- BuildDirectoryConfig
- EventLog

### API Endpoints to Implement
- `POST /api/builds` - Create + enqueue build
- `GET /api/builds/{id}/directories` - Get build directory config
- `POST /api/contexts` - Create project context
- `POST /api/contexts/{id}/scan` - Scan source directory
- `GET /api/contexts/{id}/manifest` - List scanned files
- `POST /api/prompts/templates` - Save prompt template
- `POST /api/prompts/chat` - Requirement refining chat
- `POST /api/prompts/generate` - Generate final build prompt
- `WS /ws/builds/{id}` - Real-time build events

### Agent Implementation
Each agent needs:
- Structured prompt templates
- Ollama HTTP client integration
- Response parsing and validation
- Error handling and retry logic

### Frontend Pages to Build
- **Dashboard** - Overview with quick actions
- **PromptStudio** - Chat + form + prompt generator
- **ProjectContext** - Context creation + scanner
- **BuildPipeline** - Live build table with filters
- **Artifacts** - Browse completed builds
- **BuildDetail** - Individual build view
- **Settings** - Ollama configuration, models, etc.

### WebSocket Integration
- Real-time build phase updates
- Event streaming for build progress
- Connection management and error handling

## Final System Features

When completed, your TESSR-LOGIC app will have:
- ✅ Working backend API with all routes
- ✅ Functional job queue with async processing
- ✅ Event bus for real-time updates
- ✅ Complete frontend with all pages
- ✅ Ollama integration working
- ✅ Project context scanning
- ✅ Build pipeline with phase tracking

## Next Steps After Build

Once you have the basic system working:
1. **Test the pipeline** with simple build requests
2. **Add custom agents** for specific languages/frameworks
3. **Enhance the UI** with more detailed progress tracking
4. **Add build templates** for common project types
5. **Implement build sharing** between users

## Windsurf IDE Tips

Since you're using Windsurf IDE, take advantage of these features:

### Built-in AI Assistant
- Use the AI chat panel to help debug issues
- Ask the AI to explain code sections or suggest improvements
- Use it for generating boilerplate code for agents or API endpoints

### Development Workflow
- **Multi-terminal support** - Run backend and frontend in separate terminals within Windsurf
- **File explorer** - Easy navigation of the complex directory structure
- **Integrated terminal** - Quick access to commands without leaving the IDE
- **Code completion** - Enhanced TypeScript and Python support

### Recommended Windsurf Setup
```bash
# Open project in Windsurf
# Use split view: left for backend, right for frontend
# Set up two terminals:
# Terminal 1: Backend (uvicorn command)
# Terminal 2: Frontend (npm run dev)
```

## Troubleshooting Tips

### Common Issues
1. **Ollama connection failed** - Ensure Ollama is running and models are pulled
2. **Job queue not starting** - Check async/await implementation in lifespan
3. **Pipeline phases stuck** - Verify event bus emit method is working
4. **Database errors** - Ensure SQLite file permissions are correct
5. **Frontend API errors** - Check CORS settings and API endpoints

### Using Windsurf AI for Debugging
- Paste error messages into the AI chat for explanations
- Ask the AI to review your agent implementations
- Use it to generate test cases for API endpoints
- Get help with TypeScript type errors in the frontend

### Debug Commands
```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Check backend
curl http://localhost:8000/docs

# Check database
sqlite3 tessr_logic.db ".tables"
```

This should give your buddy a complete foundation to replicate the TESSR-LOGIC system. The key is implementing each component systematically and testing the Ollama integration early.
