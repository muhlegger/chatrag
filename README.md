# Portal RAG

Retrieval-Augmented Generation portal that lets users upload PDF documents, index them locally with Chroma, and chat with an Ollama-hosted LLM whose answers are grounded on the uploaded knowledge base.

The project is intentionally small and clean so it can serve as a template for future RAG initiatives. The backend follows FastAPI best practices with clear logging, guard clauses, and background jobs for indexing. The frontend uses Vite + React + Tailwind with a minimal, accessible UI.

## Architecture

```
                    +-----------------------+
Upload PDF  --->    |  FastAPI /upload      | --+--> Background task
Ask question --->   |  FastAPI /chat        |   |    • PyPDF -> chunks
                    +-----------+-----------+   |    • Chroma persistence
                                |               |
                                v               |
                        HuggingFace Embeddings  |
                                |               |
                                v               |
                            Chroma Vector DB <---
                                |
                                v
                        RetrievalQA (Ollama LLaMA 3)
                                |
                                v
                         Frontend Chat (React)
```

## Requirements

- Python 3.11+ (tested on 3.13)
- Node.js 18+
- Ollama running locally with the `llama3` model pulled (`ollama pull llama3`)
- Git (used for versioning / deployment)

## Environment variables

| Name                | Description                                   | Default                     |
|---------------------|-----------------------------------------------|-----------------------------|
| `FRONTEND_ORIGINS`  | Comma-separated list of allowed CORS origins   | `http://localhost:5173`     |
| `UPLOAD_DIRECTORY`  | Folder used to store uploaded PDFs             | `data`                      |
| `CHROMA_DB_DIRECTORY` | Folder used to persist Chroma vectors        | `db`                        |
| `LOG_LEVEL`         | Logging level (DEBUG, INFO, …)                | `INFO`                      |

## Backend (FastAPI)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Key endpoints:

- `GET /` – health ping.
- `POST /upload/` – accepts a single PDF, writes it to disk, and dispatches indexing in the background.
- `GET /index-status/{filename}` – returns `queued | processing | done | error` plus optional error detail.
- `POST /chat/` – expects `query` form field; responds with grounded answer + per-document metadata.
- `GET /health` – exposes readiness flags for observability.

## Frontend (React + Vite + Tailwind)

```powershell
cd frontend
npm install
npm run dev
```

Vite prints the URL it is using (e.g., `http://localhost:5173`). Open it in the browser, upload a PDF, and start asking questions once the status chip reaches `done`.

To produce a production build run `npm run build` and deploy everything under `frontend/dist/`.

## Clean code highlights

- Centralised logging and guard clauses for every expensive dependency (embeddings, vector store, QA chain).
- Helper functions (`_require_runtime_ready`, `_require_chain_ready`) keep endpoints lean and expressive.
- Background processing reports progress through the `/index-status` endpoint while protecting against race conditions.
- Frontend exposes source attribution and a11y-friendly colours, plus shared CSS variables that allow future theme toggles.
- `.gitignore` keeps caches, build artefacts, and local backups out of version control.

## Verifying the stack

```powershell
# Backend type-check / lint (optional but recommended)
pip install mypy ruff
ruff check backend

# Frontend bundling check
npm run build
```

## Version control & GitHub

The repository is already initialised locally; configure your preferred remote and push whenever you are ready.

Happy building!
