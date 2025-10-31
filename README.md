# Portal RAG

Portal RAG é um workspace de Retrieval-Augmented Generation voltado para PDFs. O backend em FastAPI (LangChain + Chroma + Ollama) indexa documentos por usuário, enquanto o frontend em React entrega um chat com respostas estruturadas e citações embutidas.

## Pré-requisitos

- Python 3.11 ou superior (testado em 3.13)
- Node.js 18 ou superior
- [Ollama](https://ollama.com/) instalado e com o modelo `llama3.1:8b` disponível:
  ```powershell
  ollama pull llama3.1:8b
  ollama serve
  ```
- Windows PowerShell (ou shell equivalente)

## Variáveis de ambiente úteis

| Variável                     | Padrão                     | Propósito                                           |
|-----------------------------|----------------------------|-----------------------------------------------------|
| `SECRET_KEY`                | `change-me`                | Chave usada para assinar o JWT                     |
| `FRONTEND_ORIGINS`          | `http://localhost:5173`    | Domínios liberados no CORS                         |
| `UPLOAD_DIRECTORY`          | `data`                     | Pasta temporária para PDFs                         |
| `CHROMA_DB_DIRECTORY`       | `db`                       | Raiz da base vetorial por usuário                  |
| `OLLAMA_MODEL`              | `llama3.1:8b`              | Modelo carregado pelo servidor Ollama              |
| `OLLAMA_BASE_URL`           | `http://127.0.0.1:11434`   | Endpoint do Ollama                                 |
| `OLLAMA_TEMPERATURE`        | `0.2`                      | Temperatura usada nas gerações                     |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120`                   | Expiração do JWT em minutos                        |

## Passo a passo rápido

1. **Clone ou baixe o repositório.**
2. **Backend**
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```
   O arquivo `users.json` é criado automaticamente ao registrar o primeiro usuário.

3. **Frontend** (outro terminal)
   ```powershell
   cd frontend
   npm install
   npm run dev
   ```
   Ajuste o `frontend/.env` caso troque o host ou porta do backend. A URL padrão do Vite é `http://localhost:5173`.

4. **Fluxo no navegador**
   - Registre um usuário (e-mail + senha ≥ 8 caracteres).
   - Envie um PDF e acompanhe o status `queued → processing → done`.
   - Faça perguntas; o backend retorna resposta com resumo executivo, mapa do contexto, implicações e as fontes referenciadas.

## Estrutura

```
chatrag/
├── backend/
│   ├── main.py            # API FastAPI + autenticação JWT + pipeline RAG
│   ├── requirements.txt
│   └── users.json         # Criado automaticamente (gitignore)
├── frontend/
│   ├── src/App.tsx        # Tela de login, upload, polling e chat
│   ├── package.json
│   └── .env               # Aponta para o backend local
└── README.md
```

## Endpoints principais

- `POST /auth/register` — cadastro (email + senha ≥ 8)
- `POST /auth/login` — autenticação e emissão do JWT
- `POST /upload/` — upload de PDF e agendamento da indexação (token obrigatório)
- `GET /index-status/{filename}` — status (`queued`, `processing`, `done`, `error`)
- `POST /chat/` — consulta RAG com citações
- `GET /health` — status geral do serviço

## Checks úteis

```powershell
# Lint opcional do backend
pip install mypy ruff
ruff check backend

# Build do frontend
npm run build

# Smoke test rápido do pipeline RAG (usa LLM mockado)
python backend/_localrag_smoke.py
```

> O script `_localrag_smoke.py` executa uma cadeia RAG com retriever/LLM mockados para validar o pipeline sem depender do Ollama. Para rodar o chatbot real, deixe o `ollama serve` ativo e mantenha o modelo definido em `OLLAMA_MODEL` disponível localmente.

## Próximos passos sugeridos

- Gerar imagens Docker separadas para backend e frontend.
- Adicionar testes automatizados (`pytest` + `httpx.AsyncClient`) cobrindo upload e chat.
- Configurar logs estruturados ou rastreamento distribuído em produção.
