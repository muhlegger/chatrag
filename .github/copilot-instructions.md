## Instruções rápidas para agentes de codificação

Este repositório é um protótipo de Portal RAG (Retrieval-Augmented Generation) com frontend em React/Vite/Tailwind e backend em FastAPI + LangChain + Chroma.

Objetivo do agente: ser imediatamente produtivo — entender onde ocorrem uploads, indexação e consulta, como rodar o projeto localmente e quais arquivos editar para mudar comportamento do RAG.

- Arquitetura principal
  - Frontend: `frontend/src/App.tsx` (React + Vite). Faz POST para `/upload/` com FormData (`file`) e para `/chat/` com FormData (`query`).
  - Backend: `backend/app.py` (FastAPI). Endpoints principais: `/upload/` (salva PDF em `backend/data` e agenda indexação em background) e `/chat/` (recebe `query` e executa `qa_chain.invoke`).
  - Persistência: Chroma persiste em `backend/db` (configurado por `CHROMA_DB_DIRECTORY = "db"`).

- Comandos de desenvolvimento (PowerShell)
  - Backend:
    ```powershell
    cd backend
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    uvicorn app:app --reload
    ```
  - Frontend:
    ```powershell
    cd frontend
    npm install
    npm run dev
    ```

- Padrões e convenções importantes
  - O backend concentra configuração e lógica em `backend/app.py` (modelos, prompt, vectorstore, endpoints). Alterações de modelo ou autenticação normalmente exigem editar esse arquivo.
  - Uploads ficam temporariamente em `backend/data` e são removidos após indexação (veja `process_and_index_pdf`).
  - A indexação é assíncrona: `/upload/` retorna imediatamente e o processamento é feito via `BackgroundTasks` — não há polling por status hoje.
  - Prompt template: `qa_prompt` em `app.py` determina comportamento do LLM (força a resposta apenas com base no contexto). Exemplos de alteração ficam nesse arquivo.

- Integrações e pontos de atenção
  - API key do LLM está hard-coded em `backend/app.py` (variável `API_KEY`). Preferir usar variáveis de ambiente (ex.: `os.getenv`) e não commitar chaves.
  - `backend/check_models.py` tenta usar `google.generativeai` mas tem uso incorreto de `os.getenv(...)` com a chave em vez do nome da variável — use ENV var corretamente.
  - CORS está limitado a `http://localhost:5173` em `app.py`; atualize se o frontend for servido de outro host/porta.
  - O README contém um erro de formatação na linha de ativação do venv; siga os comandos PowerShell acima.

- Exemplos específicos (baseados no código)
  - Upload (frontend): `fetch('http://127.0.0.1:8000/upload/', { method: 'POST', body: formData })` onde `formData` tem `file` — ver `frontend/src/App.tsx`.
  - Chat: `fetch('http://127.0.0.1:8000/chat/', { method: 'POST', body: formData })` onde `formData.append('query', question)` — resposta JSON tem `answer` e `sources`.
  - Indexação: `process_and_index_pdf()` usa `PyPDFLoader`, `RecursiveCharacterTextSplitter` (chunk_size=1500, chunk_overlap=200), e `vectordb.add_documents(...); vectordb.persist()` — veja `backend/app.py`.

- Erros e pontos a corrigir que o agente deve sinalizar
  - Remover chave hard-coded e migrar para variáveis de ambiente; documentar como definir `GOOGLE_API_KEY` (ou nome preferido).
  - Corrigir `backend/check_models.py` para `genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))` e instruir sobre como listar modelos.
  - Adicionar um endpoint ou mecanismo para checar o status da indexação (opcional), pois hoje a UX do frontend assume completude imediata.

Se alguma parte estiver incompleta ou quiser que eu detalhe exemplos de PRs/edits (ex.: mover API_KEY para env, adicionar status endpoint, testes unitários minimalistas), diga qual alteração prefere e eu implemento.
