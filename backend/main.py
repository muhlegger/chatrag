"""Backend FastAPI do Portal RAG."""

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
Voce atua como assistente de recuperacao. Responda somente com o contexto abaixo.
Se nao houver informacao, diga "Com base nos documentos enviados nao encontrei resposta.".
Sempre cite nome do arquivo e pagina quando possivel.

CONTEXTO:
{context}

PERGUNTA:
{question}
"""

def build_embeddings() -> Optional[HuggingFaceEmbeddings]:  # type: ignore[name-defined]
    if not IMPORT_OK:
        logger.warning("Dependencias do LangChain ausentes: %s", IMPORT_ERR)
        return None
    try:
        logger.info("Carregando embeddings sentence-transformers")
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    except Exception as exc:
        logger.exception("Falha ao carregar embeddings: %s", exc)
        return None

def build_vectorstore(embeddings: Optional[HuggingFaceEmbeddings]):  # type: ignore[name-defined]
    if embeddings is None:
        return None
    try:
        logger.info("Conectando ao Chroma em %s", VECTOR_DB_DIR)
        return Chroma(persist_directory=str(VECTOR_DB_DIR), embedding_function=embeddings)
    except Exception as exc:
        logger.exception("Falha ao iniciar Chroma: %s", exc)
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
        logger.exception("Falha ao montar cadeia RAG: %s", exc)
        return None

embeddings = build_embeddings()
vectordb = build_vectorstore(embeddings)
qa_chain = build_qa_chain(vectordb)

app = FastAPI(
    title="Portal RAG API",
    description="Envie PDFs e consulte respostas ancoradas em contexto local com Ollama.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", summary="Status da API")
async def root():
    """Ping simples para monitoramento."""
    return {"status": "ok", "message": "Backend Portal RAG ativo."}

index_status: Dict[str, StatusLiteral] = {}
index_errors: Dict[str, str] = {}


def _ensure_ready(component: Optional[object], name: str) -> Optional[JSONResponse]:
    """Retorna 503 caso o componente necessario nao esteja pronto."""
    if component is None:
        return JSONResponse(status_code=503, content={"error": f"{name} nao inicializado."})
    return None


async def _require_runtime_ready() -> Optional[JSONResponse]:
    if resp := _ensure_ready(embeddings, "Embeddings"):  # noqa: SIM108
        return resp
    if resp := _ensure_ready(vectordb, "Base vetorial"):
        return resp
    return None

async def _require_chain_ready() -> Optional[JSONResponse]:
    base_check = await _require_runtime_ready()
    if base_check is not None:
        return base_check
    if resp := _ensure_ready(qa_chain, "Cadeia RAG"):
        return resp
    return None

@app.post("/upload/", summary="Enviar e indexar PDF")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if resp := await _require_runtime_ready():
        return resp
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse(status_code=400, content={"error": "Apenas PDFs sao aceitos."})
    if (file.content_type or "").lower() != "application/pdf":
        return JSONResponse(status_code=400, content={"error": "Content-Type invalido para PDF."})

    file_path = UPLOAD_DIR / file.filename
    try:
        payload = await file.read()
        if len(payload) < 10:
            return JSONResponse(status_code=400, content={"error": "Arquivo vazio ou corrompido."})
        file_path.write_bytes(payload)
    except Exception as exc:
        logger.exception("Erro ao salvar arquivo enviado: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Nao foi possivel salvar o arquivo."})

    index_status[file.filename] = "queued"
    index_errors.pop(file.filename, None)
    background_tasks.add_task(process_and_index_pdf, file_path, file.filename)
    return {"status": "ok", "message": f"Arquivo '{file.filename}' aguardando indexacao."}

@app.get("/index-status/{filename}", summary="Consultar status de indexacao")
async def index_status_endpoint(filename: str):
    status = index_status.get(filename)
    if status is None:
        return JSONResponse(status_code=404, content={"error": "Arquivo nao encontrado."})
    return {"filename": filename, "status": status, "detail": index_errors.get(filename)}

@app.post("/chat/", summary="Consultar PDFs indexados")
async def chat(query: str = Form(...)):
    if not query:
        return JSONResponse(status_code=400, content={"error": "A pergunta nao pode ser vazia."})
    if resp := await _require_chain_ready():
        return resp

    logger.info("Pergunta recebida: %s", query)
    try:
        result = qa_chain.invoke({"query": query})  # type: ignore[union-attr]
    except Exception as exc:
        logger.exception("Falha na cadeia RAG: %s", exc)
        return JSONResponse(status_code=500, content={"error": "Erro ao consultar o LLM."})

    answer = result.get("result", "Nao foi possivel gerar resposta.")
    sources_payload = []
    seen = set()
    for document in result.get("source_documents", []):
        meta = document.metadata or {}
        src = meta.get("source", "desconhecido")
        page = meta.get("page")
        key = (src, page)
        if key in seen:
            continue
        seen.add(key)
        sources_payload.append({"source": src, "page": page})

    return {"answer": answer, "sources": sources_payload}

@app.get("/health", summary="Health check")
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
    logger.info("Inicio da indexacao em segundo plano para %s", filename)
    if vectordb is None:
        index_status[filename] = "error"
        index_errors[filename] = "Base vetorial indisponivel"
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
        logger.info("Arquivo %s indexado em %d trechos", filename, len(chunks))
    except Exception as exc:
        index_status[filename] = "error"
        index_errors[filename] = str(exc)
        logger.exception("Erro durante indexacao de %s: %s", filename, exc)
    finally:
        try:
            if index_status.get(filename) == "done":
                file_path.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.warning("Falha ao remover arquivo temporario %s: %s", file_path, cleanup_exc)

*** End of File

