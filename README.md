# Portal RAG

Portal RAG é um workspace de RAG (Retrieval-Augmented Generation) focado em PDFs. O backend recebe o arquivo, quebra em trechos, grava os vetores no Chroma e usa o Ollama (LLaMA 3) para responder. O frontend entrega um chat único com contexto exibido de forma transparente.

## Visão geral

- **Backend:** FastAPI + LangChain + Chroma + Ollama.
- **Frontend:** React + Vite + Tailwind com paleta suave e chips de fonte.
- **Fluxo:**
  1. `/upload/` salva o PDF e agenda indexação em background.
  2. PyPDF divide o texto, embeddings são persistidos em `CHROMA_DB_DIRECTORY`.
  3. `/chat/` executa RetrievalQA (top‑5 chunks) e devolve resposta + arquivo/página.

```
PDF -> FastAPI /upload -> tarefa assíncrona -> Chroma -> RetrievalQA (Ollama) -> /chat -> React
```

## Requisitos

- Python 3.11+ (testado em 3.13)
- Node.js 18+
- Ollama com o modelo `llama3` já baixado (`ollama pull llama3`)
- Git

## Variáveis de ambiente

| Variável | Função | Default |
| --- | --- | --- |
| `FRONTEND_ORIGINS` | Origens liberadas no CORS | `http://localhost:5173` |
| `UPLOAD_DIRECTORY` | Pasta temporária dos PDFs | `data` |
| `CHROMA_DB_DIRECTORY` | Persistência do Chroma | `db` |
| `LOG_LEVEL` | Nível de log | `INFO` |

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Rotas principais:
- `GET /` – ping
- `POST /upload/` – salva PDF e dispara indexação
- `GET /index-status/{filename}` – `queued | processing | done | error`
- `POST /chat/` – espera `query` e devolve resposta com fontes
- `GET /health` – flags de prontidão

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

Abra o endereço mostrado pelo Vite (padrão `http://localhost:5173`). Faça upload, aguarde o chip mostrar `done` e pergunte. Para gerar build final, use `npm run build` e publique o conteúdo de `dist/`.

## Boas práticas em uso

- Helpers de prontidão bloqueiam chamadas se embeddings/Chroma/QA não estiverem carregados.
- Indexação em background loga progresso e expõe erros via `/index-status`.
- Cada resposta cita arquivo e página para rastreabilidade.
- Tema baseado em variáveis CSS facilita ajustes de cor e compatibiliza modos claro/escuro.

## Checks rápidos

```powershell
# opcionais
pip install mypy ruff
ruff check backend

npm run build
```
