"""Portal RAG FastAPI backend."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

StatusLiteral = Literal["queued", "processing", "done", "error"]

IMPORT_OK = True
IMPORT_ERR = None
try:  # pragma: no cover
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_community.llms import Ollama
    from langchain_community.vectorstores import Chroma
    from langchain.chains import RetrievalQA
    from langchain.prompts import PromptTemplate
    from langchain.text_splitter import RecursiveCharacterTextSplitter
except ModuleNotFoundError as exc:  # pragma: no cover
    IMPORT_OK = False
    IMPORT_ERR = str(exc)
    try:
        from langchain.document_loaders import PyPDFLoader  # type: ignore
        from langchain.embeddings import HuggingFaceEmbeddings  # type: ignore
        from langchain.llms import Ollama  # type: ignore
        from langchain.vectorstores import Chroma  # type: ignore
        from langchain.chains import RetrievalQA
        from langchain.prompts import PromptTemplate
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        IMPORT_OK = True
        IMPORT_ERR = None
    except Exception as fallback_exc:  # pragma: no cover
        IMPORT_ERR = f"{IMPORT_ERR}; fallback failed: {fallback_exc}"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("portal-rag")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIRECTORY", "data"))
VECTOR_DB_DIR = Path(os.getenv("CHROMA_DB_DIRECTORY", "db"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

def _origins_from_env() -> List[str]:
    raw = os.getenv("FRONTEND_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

ALLOWED_ORIGINS = _origins_from_env()
PROMPT_TEMPLATE = """
You are a focused retrieval assistant. Answer strictly with the context below.
If the answer is not present, say "Based on the uploaded documents I could not find an answer.".
Cite the filename and page whenever possible.

CONTEXT:
{context}

QUESTION:
{question}
"""

def build_embeddings() -> Optional[HuggingFaceEmbeddings]:  # type: ignore[name-defined]
    if not IMPORT_OK:
        logger.warning("LangChain dependencies missing: %s", IMPORT_ERR)
        return None
    try:
        logger.info("Loading sentence-transformers embeddings")
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    except Exception as exc:
        logger.exception("Could not load embeddings: %s", exc)
        return None

def build_vectorstore(embeddings: Optional[HuggingFaceEmbeddings]):  # type: ignore[name-defined]
    if embeddings is None:
        return None
    try:
        logger.info("Connecting to Chroma vector store at %s", VECTOR_DB_DIR)
        return Chroma(persist_directory=str(VECTOR_DB_DIR), embedding_function=embeddings)
    except Exception as exc:
        logger.exception("Could not initialise vector store: %s", exc)
        return None

def build_qa_chain(vectorstore):
    if vectorstore is None:
        return None
    prompt = PromptTemplate(template=PROMPT_TEMPLATE, input_variables=["context", "question"])
    try:
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        return RetrievalQA.from_chain_type(
            Ollama(model="llama3", base_url="http://127.0.0.1:11434", temperature=0.2),
            retriever=retriever,
            chain_type="stuff",
            chain_type_kwargs={"prompt": prompt},
            return_source_documents=True,
        )
    except Exception as exc:
        logger.exception("Could not build QA chain: %s", exc)
        return None

embeddings = build_embeddings()
vectordb = build_vectorstore(embeddings)
qa_chain = build_qa_chain(vectordb)

app = FastAPI(
    title="Portal RAG API",
    description="Upload PDFs and query an Ollama-powered RAG pipeline.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", summary="Service status")
async def root():
    """Simple ping endpoint used by monitors."""
    return {"status": "ok", "message": "Portal RAG backend is running."}

index_status: Dict[str, StatusLiteral] = {}
index_errors: Dict[str, str] = {}


def _ensure_ready(component: Optional[object], name: str) -> Optional[JSONResponse]:
    """Return a 503 JSON response if a runtime dependency has not been initialised."""
    if component is None:
        return JSONResponse(status_code=503, content={"error": f"{name} is not initialised."})
    return None


async def _require_runtime_ready() -> Optional[JSONResponse]:
    if resp := _ensure_ready(embeddings, "Embeddings"):  # noqa: SIM108
        return resp
    if resp := _ensure_ready(vectordb, "Vector store"):
        return resp
    return None

async def _require_chain_ready() -> Optional[JSONResponse]:
    base_check = await _require_runtime_ready()
    if base_check is not None:
        return base_check
    if resp := _ensure_ready(qa_chain, "Retrieval QA chain"):
        return resp
    return None

@app.post("/upload/", summary="Upload & index a PDF")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if resp := await _require_runtime_ready():
        return resp
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Only PDF files are supported."})
    if (file.content_type or "").lower() != "application/pdf":
        return JSONResponse(status_code=400, content={"error": "Invalid content type for PDF."})

    file_path = UPLOAD_DIR / file.filename
    try:
        payload = await file.read()
        if len(payload) < 10:
            return JSONResponse(status_code=400, content={"error": "Empty or corrupted file."})
        file_path.write_bytes(payload)
    except Exception as exc:
        logger.exception("Failed to persist uploaded file: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Could not save file."})

    index_status[file.filename] = "queued"
    index_errors.pop(file.filename, None)
    background_tasks.add_task(process_and_index_pdf, file_path, file.filename)
    return {"status": "ok", "message": f"File '{file.filename}' queued for processing."}

@app.get("/index-status/{filename}", summary="Check indexing status")
async def index_status_endpoint(filename: str):
    status = index_status.get(filename)
    if status is None:
        return JSONResponse(status_code=404, content={"error": "File not found."})
    return {"filename": filename, "status": status, "detail": index_errors.get(filename)}

@app.post("/chat/", summary="Ask a question against indexed PDFs")
async def chat(query: str = Form(...)):
    if not query:
        return JSONResponse(status_code=400, content={"error": "Query is required."})
    if resp := await _require_chain_ready():
        return resp

    logger.info("Received question: %s", query)
    try:
        result = qa_chain.invoke({"query": query})  # type: ignore[union-attr]
    except Exception as exc:
        logger.exception("RAG pipeline failed: %s", exc)
        return JSONResponse(status_code=500, content={"error": "LLM retrieval failed."})

    answer = result.get("result", "No answer could be generated.")
    sources_payload = []
    seen = set()
    for document in result.get("source_documents", []):
        meta = document.metadata or {}
        src = meta.get("source", "unknown")
        page = meta.get("page")
        key = (src, page)
        if key in seen:
            continue
        seen.add(key)
        sources_payload.append({"source": src, "page": page})

    return {"answer": answer, "sources": sources_payload}

@app.get("/health", summary="API health check")
async def health():
    return {
        "status": "ok",
        "langchain_ready": IMPORT_OK,
        "embeddings_loaded": embeddings is not None,
        "vector_store_ready": vectordb is not None,
        "qa_chain_ready": qa_chain is not None,
        "allowed_origins": ALLOWED_ORIGINS,
    }

def process_and_index_pdf(file_path: Path, filename: str):
    logger.info("Starting background indexing for %s", filename)
    if vectordb is None:
        index_status[filename] = "error"
        index_errors[filename] = "Vector store unavailable"
        return
    index_status[filename] = "processing"
    try:
        loader = PyPDFLoader(str(file_path))
        documents = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=1500, chunk_overlap=200)
        chunks = splitter.split_documents(documents)
        vectordb.add_documents(chunks)
        vectordb.persist()
        index_status[filename] = "done"
        logger.info("Indexed %s into %d chunks", filename, len(chunks))
    except Exception as exc:
        index_status[filename] = "error"
        index_errors[filename] = str(exc)
        logger.exception("Error while indexing %s: %s", filename, exc)
    finally:
        try:
            if index_status.get(filename) == "done":
                file_path.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.warning("Could not remove temp file %s: %s", file_path, cleanup_exc)

*** End of File
