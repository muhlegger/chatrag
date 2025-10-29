# Portal RAG

Portal RAG é um workspace de Retrieval-Augmented Generation focado em PDFs. O backend (FastAPI + LangChain + Chroma + Ollama) indexa os documentos por usuário e o frontend (React + Vite + Tailwind) entrega o chat com fontes exibidas no próprio texto.

## Pré-requisitos

- Python 3.11 ou superior (testado em 3.13)
- Node.js 18 ou superior
- [Ollama](https://ollama.com/) instalado e com o modelo **llama3.1:8b** baixado:
  ```powershell
  ollama pull llama3.1:8b
  ```
- Windows PowerShell (comandos abaixo) ou shell equivalente

## Como rodar (clone ou .zip)

1. Descompacte o projeto ou faça `git clone`.
2. Entre na pasta `backend/`:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   > Variáveis opcionais: `SECRET_KEY` (segredo do JWT), `FRONTEND_ORIGINS`, `UPLOAD_DIRECTORY`, `CHROMA_DB_DIRECTORY`. Caso não configure, os valores padrão definidos no código serão usados.

3. Com a venv ativa, inicie a API:
   ```powershell
   uvicorn main:app --reload --port 8000
   ```

4. (Primeiros passos) A API criará automaticamente `backend/users.json` caso não exista. Use o frontend para cadastrar usuários.

5. Em outro terminal, prepare o frontend:
   ```powershell
   cd ..rontend
   npm install
   npm run dev
   ```
   - O arquivo `frontend/.env` já aponta para `http://127.0.0.1:8000`. Ajuste apenas se mudar o host/porta do backend.
   - O Vite informará a URL (por padrão `http://localhost:5173`).

6. Fluxo no navegador:
   - Cadastre uma conta no formulário inicial (o frontend usa JWT e isola os PDFs por usuário).
   - Faça upload de um PDF; acompanhe o status (queued → processing → done).
   - Envie perguntas; as respostas vêm formatadas com “Resumo executivo”, “Mapa do contexto”, “Implicações” e as fontes incorporadas ao texto.

## Estrutura

```
portal-rag/
├── backend/
│   ├── main.py              # API FastAPI + autenticação JWT + Chroma per-user
│   ├── requirements.txt
│   └── users.json           # criado/atualizado automaticamente
├── frontend/
│   ├── src/App.tsx          # Tela de login, upload e chat
│   ├── package.json
│   └── .env                 # aponta para o backend
└── README.md
```

## Rotas principais do backend

- `POST /auth/register` – cria usuário (email + senha ≥ 8 caracteres)
- `POST /auth/login` – devolve JWT
- `POST /upload/` – recebe PDF e agenda indexação (requires Bearer token)
- `GET /index-status/{filename}` – retorna `queued | processing | done | error`
- `POST /chat/` – responde usando o RAG do usuário logado
- `GET /health` – status geral (lista usuários com cache carregado)

## Observações importantes

- **Modelo Ollama**: `llama3.1:8b` precisa estar rodando localmente (`ollama serve`).
- **Armazenamento**: PDFs temporários ficam em `backend/data/<slug-do-usuário>` e o banco vetorial em `backend/db/<slug>`. Cada usuário enxerga apenas seus documentos.
- **Chunking**: cada PDF é dividido em blocos de 2 200 caracteres (overlap 400) e o retriever consulta os 12 blocos mais relevantes por pergunta para respostas mais completas.
- **Produção**: use um `SECRET_KEY` forte e considere rodar sem `--reload`. Para liberar a API externamente, ajuste CORS (`FRONTEND_ORIGINS`).

## Checks rápidos

```powershell
# Opcional: lint do backend
pip install mypy ruff
ruff check backend

# Build frontend
npm run build
```

Qualquer dúvida ou melhoria desejada, abra uma issue ou adapte o prompt/arquitetura conforme o seu cenário.
