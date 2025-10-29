"""Backend FastAPI do Portal RAG."""

from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    UploadFile,
    HTTPException,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import Ollama
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter

StatusLiteral = Literal["queued", "processing", "done", "error"]

# --- Configurações de autenticação ---
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))
USERS_DB_PATH = Path(os.getenv("USERS_DB_PATH", "users.json"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# --- Estruturas globais ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("portal-rag")

UPLOAD_ROOT = Path(os.getenv("UPLOAD_DIRECTORY", "data"))
VECTOR_DB_ROOT = Path(os.getenv("CHROMA_DB_DIRECTORY", "db"))
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
VECTOR_DB_ROOT.mkdir(parents=True, exist_ok=True)

vector_store_cache: Dict[str, Optional[Chroma]] = {}
qa_chain_cache: Dict[str, Optional[RetrievalQA]] = {}
index_status: Dict[str, Dict[str, StatusLiteral]] = defaultdict(dict)
index_errors: Dict[str, Dict[str, str]] = defaultdict(dict)

# --- Modelos Pydantic ---


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class AuthResponse(BaseModel):
    message: str


# --- Funções de persistência de usuários ---


def _load_users() -> Dict[str, Dict[str, str]]:
    if not USERS_DB_PATH.exists():
        USERS_DB_PATH.write_text("{}", encoding="utf-8")
        return {}
    try:
        return json.loads(USERS_DB_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Arquivo de usuarios corrompido; reiniciando banco.")
        USERS_DB_PATH.write_text("{}", encoding="utf-8")
        return {}


def _save_users(users: Dict[str, Dict[str, str]]) -> None:
    USERS_DB_PATH.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _get_user(email: str) -> Optional[Dict[str, str]]:
    users = _load_users()
    return users.get(email)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(email: str, password: str) -> Optional[Dict[str, str]]:
    user = _get_user(email)
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def slugify_user(email: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "_", email.lower())


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None
    if _get_user(email.lower()) is None:
        raise credentials_exception
    return email.lower()


# --- Funções auxiliares de armazenamento vetorial ---

PROMPT_TEMPLATE = """
Voce atua como um especialista em RAG. Responda EXCLUSIVAMENTE em portugues do Brasil.

Sua tarefa e construir respostas exaustivas, minuciosas e fundamentadas, usando SOMENTE o CONTEUDO informado em CONTEXTO.
Jamais use conhecimento externo.

Caso o contexto nao traga informacoes suficientes, escreva exatamente:
"Nao encontrei a resposta nos documentos enviados."

Siga este formato de resposta:

Resumo executivo:
- Produza 2 frases concisas que apresentem a ideia central e o objetivo principal do contexto.

Mapa do contexto:
- Comece listando os temas principais em uma estrutura numerada (1., 2., ...).
- Para cada tema, crie subtitulos e redija paragrafos completos (minimo 4 frases), explorando todos os detalhes existentes.
- Use marcadores hierarquicos (1., 1.1., 1.1.1) para descrever classificacoes, diagnosticos diferenciais, fases clinicas, sintomas, dados epidemiologicos, mecanismos fisiopatologicos e tratamentos.
- Transcreva todos os valores numericos, faixas etarias, percentuais, escalas, cut-offs, datas e exemplos.
- Se o contexto mencionar tabelas ou quadros, converta cada linha em frases preservando as relacoes entre colunas.
- Se o contexto mencionar estudos, cite ano, amostra, metodologia e conclusoes.
- Se existirem lacunas, divergencias ou hipoteses, registre-as explicitamente em uma subseccao "Pontos em aberto".

Implicacoes e condutas:
- Liste, em ordem de prioridade, as condutas praticas, riscos, precaucoes, recomendacoes, follow-up ou impacto terapeutico descritos.
- Caso nao haja orientacoes aplicaveis, escreva "Nao ha acoes adicionais no contexto.".

Regras finais:
- Use conectivos que reforcem a logica do texto (portanto, entretanto, alem disso, consequentemente).
- Evite repeticoes, nao adicione "Fontes:" e nunca use conhecimento fora do contexto.
- Termine cada subtitulo apenas quando todos os detalhes relacionados estiverem cobertos.
Nao repita frases desnecessarias, nao adicione "Fontes:" e nao use conhecimento externo.

CONTEXTO:
{context}

PERGUNTA:
{question}

RESPOSTA:
"""



def ensure_user_dirs(user_slug: str) -> tuple[Path, Path]:
    upload_dir = UPLOAD_ROOT / user_slug
    vectordb_dir = VECTOR_DB_ROOT / user_slug
    upload_dir.mkdir(parents=True, exist_ok=True)
    vectordb_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir, vectordb_dir


def get_vectordb_for_user(user_slug: str) -> Optional[Chroma]:
    if user_slug in vector_store_cache:
        return vector_store_cache[user_slug]
    if embeddings is None:
        return None
    _, vectordb_dir = ensure_user_dirs(user_slug)
    vector_store_cache[user_slug] = Chroma(
        persist_directory=str(vectordb_dir),
        embedding_function=embeddings,
    )
    return vector_store_cache[user_slug]


def reset_user_chain(user_slug: str) -> None:
    qa_chain_cache.pop(user_slug, None)


def get_qa_chain_for_user(user_slug: str) -> Optional[RetrievalQA]:
    if user_slug in qa_chain_cache:
        return qa_chain_cache[user_slug]
    vectordb = get_vectordb_for_user(user_slug)
    if vectordb is None:
        qa_chain_cache[user_slug] = None
        return None
    prompt = PromptTemplate(
        template=PROMPT_TEMPLATE, input_variables=["context", "question"]
    )
    retriever = vectordb.as_retriever(search_kwargs={"k": 12})
    qa_chain_cache[user_slug] = RetrievalQA.from_chain_type(
        Ollama(model="llama3.1:8b", base_url="http://127.0.0.1:11434", temperature=0.2),
        retriever=retriever,
        chain_type="stuff",
        chain_type_kwargs={"prompt": prompt},
        return_source_documents=True,
    )
    return qa_chain_cache[user_slug]


# --- Inicialização de embeddings ---

embeddings = None
try:
    logger.info("Carregando embeddings sentence-transformers")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
except Exception as exc:
    logger.exception("Falha ao carregar embeddings: %s", exc)

app = FastAPI(
    title="Portal RAG API",
    description="Envie PDFs e consulte respostas ancoradas em contexto local com Ollama.",
    version="3.0.0",
)

frontend_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/register", status_code=201, response_model=AuthResponse)
async def register_user(payload: UserCreate) -> AuthResponse:
    users = _load_users()
    email = payload.email.lower()
    if email in users:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    password = payload.password
    if len(password) < 8 or len(password) > 128:
        raise HTTPException(
            status_code=400, detail="Senha deve ter entre 8 e 128 caracteres."
        )

    users[email] = {
        "hashed_password": get_password_hash(password),
        "created_at": datetime.utcnow().isoformat(),
    }
    _save_users(users)
    return AuthResponse(message="Usuário criado com sucesso.")


@app.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    email = form_data.username.lower()
    user = authenticate_user(email, form_data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Credenciais inválidas.")
    access_token = create_access_token({"sub": email})
    return Token(access_token=access_token, token_type="bearer")


@app.get("/", summary="Status da API")
async def root() -> Dict[str, str]:
    return {"status": "ok", "message": "Backend Portal RAG ativo."}


def _ensure_ready(component: Optional[object], name: str) -> Optional[JSONResponse]:
    if component is None:
        return JSONResponse(
            status_code=503, content={"error": f"{name} nao inicializado."}
        )
    return None


async def _require_runtime_ready(user_slug: str) -> Optional[JSONResponse]:
    if resp := _ensure_ready(embeddings, "Embeddings"):  # noqa: SIM108
        return resp
    if get_vectordb_for_user(user_slug) is None:
        return JSONResponse(
            status_code=503, content={"error": "Base vetorial indisponivel."}
        )
    return None


async def _require_chain_ready(user_slug: str) -> Optional[JSONResponse]:
    if resp := await _require_runtime_ready(user_slug):
        return resp
    if get_qa_chain_for_user(user_slug) is None:
        return JSONResponse(
            status_code=503, content={"error": "Cadeia RAG indisponivel."}
        )
    return None


@app.post("/upload/", summary="Enviar e indexar PDF")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user),
):
    user_slug = slugify_user(current_user)
    if resp := await _require_runtime_ready(user_slug):
        return resp
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse(
            status_code=400, content={"error": "Apenas PDFs sao aceitos."}
        )
    if (file.content_type or "").lower() != "application/pdf":
        return JSONResponse(
            status_code=400, content={"error": "Content-Type invalido para PDF."}
        )

    upload_dir, _ = ensure_user_dirs(user_slug)
    file_path = upload_dir / file.filename
    try:
        payload = await file.read()
        if len(payload) < 10:
            return JSONResponse(
                status_code=400, content={"error": "Arquivo vazio ou corrompido."}
            )
        file_path.write_bytes(payload)
    except Exception as exc:
        logger.exception("Erro ao salvar arquivo enviado: %s", exc)
        return JSONResponse(
            status_code=500, content={"error": "Nao foi possivel salvar o arquivo."}
        )

    index_status[user_slug][file.filename] = "queued"
    index_errors[user_slug].pop(file.filename, None)
    background_tasks.add_task(
        process_and_index_pdf, user_slug, file_path, file.filename
    )
    return {
        "status": "ok",
        "message": f"Arquivo '{file.filename}' aguardando indexacao.",
    }


@app.get("/index-status/{filename}", summary="Consultar status de indexacao")
async def index_status_endpoint(
    filename: str,
    current_user: str = Depends(get_current_user),
):
    user_slug = slugify_user(current_user)
    status_value = index_status[user_slug].get(filename)
    if status_value is None:
        return JSONResponse(
            status_code=404, content={"error": "Arquivo nao encontrado."}
        )
    return {
        "filename": filename,
        "status": status_value,
        "detail": index_errors[user_slug].get(filename),
    }


@app.post("/chat/", summary="Consultar PDFs indexados")
async def chat(
    query: str = Form(...),
    current_user: str = Depends(get_current_user),
):
    if not query:
        return JSONResponse(
            status_code=400, content={"error": "A pergunta nao pode ser vazia."}
        )
    user_slug = slugify_user(current_user)
    if resp := await _require_chain_ready(user_slug):
        return resp

    chain = get_qa_chain_for_user(user_slug)
    if chain is None:
        return JSONResponse(
            status_code=503, content={"error": "Cadeia RAG indisponivel."}
        )

    logger.info("Pergunta recebida de %s: %s", current_user, query)
    try:
        result = chain.invoke({"query": query})
    except Exception as exc:
        logger.exception("Falha na cadeia RAG: %s", exc)
        return JSONResponse(
            status_code=500, content={"error": "Erro ao consultar o LLM."}
        )

    answer = result.get("result", "Nao foi possivel gerar resposta.")
    sources_payload: List[Dict[str, Optional[int]]] = []
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
async def health() -> Dict[str, object]:
    return {
        "status": "ok",
        "embeddings_loaded": embeddings is not None,
        "vector_caches": list(vector_store_cache.keys()),
    }


def process_and_index_pdf(user_slug: str, file_path: Path, filename: str) -> None:
    logger.info(
        "Inicio da indexacao em segundo plano para %s (%s)", filename, user_slug
    )
    vectordb = get_vectordb_for_user(user_slug)
    if vectordb is None:
        index_status[user_slug][filename] = "error"
        index_errors[user_slug][filename] = "Base vetorial indisponivel"
        return

    index_status[user_slug][filename] = "processing"
    try:
        loader = PyPDFLoader(str(file_path))
        documents = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=2200, chunk_overlap=400)
        chunks = splitter.split_documents(documents)
        vectordb.add_documents(chunks)
        vectordb.persist()
        index_status[user_slug][filename] = "done"
        reset_user_chain(user_slug)
        logger.info("Arquivo %s indexado em %d trechos", filename, len(chunks))
    except Exception as exc:
        index_status[user_slug][filename] = "error"
        index_errors[user_slug][filename] = str(exc)
        logger.exception("Erro durante indexacao de %s: %s", filename, exc)
    finally:
        try:
            if index_status[user_slug].get(filename) == "done":
                file_path.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.warning(
                "Falha ao remover arquivo temporario %s: %s", file_path, cleanup_exc
            )
