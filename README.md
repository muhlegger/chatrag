# Portal RAG

Portal RAG is a Retrieval-Augmented Generation workspace. Users upload PDFs, the backend indexes them with Chroma, and the chat UI asks Ollama for answers backed by those documents.

## Overview

- **Backend:** FastAPI + LangChain + Chroma, with Ollama (LLaMA 3) as the LLM.
- **Frontend:** React + Vite + Tailwind, focused on a clean chat experience and clear source attribution.
- **Data flow:**
  1. PDF upload hits `/upload/` and is queued for background processing.
  2. PyPDF splits text, embeddings are stored in Chroma on disk.
  3. `/chat/` runs a RetrievalQA chain (top-5 chunks) and returns the answer plus file/page metadata.

```
PDF -> FastAPI /upload --background--> PyPDF -> Chroma -> Ollama RetrievalQA -> FastAPI /chat -> React chat
```

## Requirements

- Python 3.11+ (tested on 3.13)
- Node.js 18+
- Ollama running locally with `llama3` downloaded (`ollama pull llama3`)
- Git for version control/deployment

## Environment variables

| Variable              | Purpose                                | Default                   |
|-----------------------|----------------------------------------|---------------------------|
| `FRONTEND_ORIGINS`    | Allowed CORS origins                    | `http://localhost:5173`   |
| `UPLOAD_DIRECTORY`    | Folder for temporary PDFs               | `data`                    |
| `CHROMA_DB_DIRECTORY` | Folder for Chroma persistence           | `db`                      |
| `LOG_LEVEL`           | Logging level                           | `INFO`                    |

## Backend setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Endpoints:
- `GET /` simple ping
- `POST /upload/` saves the PDF and triggers background indexing
- `GET /index-status/{filename}` returns `queued | processing | done | error`
- `POST /chat/` expects a `query` form field and answers with sources
- `GET /health` exposes readiness flags

## Frontend setup

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (default `http://localhost:5173`). Upload a PDF, wait until the status chip shows `done`, and then start asking questions. Build for production with `npm run build` and deploy the `dist/` folder.

## Code style highlights

- Guard helpers ensure embeddings, Chroma and the QA chain exist before serving traffic.
- Background indexing logs progress and surfaces errors through `/index-status`.
- Source attribution always includes filename + page in the UI so answers are traceable.
- The Tailwind theme relies on CSS variables for quick color adjustments and light/dark parity.

## Quick checks

```powershell
# optional linters
pip install mypy ruff
ruff check backend

# frontend bundle
npm run build
```

The repository is already initialised locally—add a remote of your choice and push when ready.
