import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

type SourceMeta = { source: string; page?: number };
type IndexStatus = "idle" | "queued" | "processing" | "done" | "error";
type Msg = { sender: "user" | "bot"; text: string };

type TokenResponse = { access_token: string; token_type: string };

type ApiError = Error & { status?: number };

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";
const STORAGE_TOKEN_KEY = "portal-rag-token";
const STORAGE_EMAIL_KEY = "portal-rag-email";

const STATUS_LABEL: Record<Exclude<IndexStatus, "idle">, string> = {
  queued: "aguardando",
  processing: "processando",
  done: "finalizado",
  error: "erro",
};

const authHeaders = (token: string): Record<string, string> =>
  token ? { Authorization: `Bearer ${token}` } : {};

async function apiRegister(email: string, password: string) {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const text = await res.text();
    const error: ApiError = new Error(text || "Falha ao registrar.") as ApiError;
    error.status = res.status;
    throw error;
  }
  return res.json();
}

async function apiLogin(email: string, password: string): Promise<TokenResponse> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const text = await res.text();
    const error: ApiError = new Error(text || "Falha ao entrar.") as ApiError;
    error.status = res.status;
    throw error;
  }
  return res.json();
}

async function apiUpload(file: File, token: string) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload/`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    const error: ApiError = new Error(text || "Erro no upload.") as ApiError;
    error.status = res.status;
    throw error;
  }
  return res.json() as Promise<{ status: string; message: string }>;
}

async function apiStatus(filename: string, token: string) {
  const res = await fetch(`${API_BASE}/index-status/${encodeURIComponent(filename)}` , {
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const text = await res.text();
    const error: ApiError = new Error(text || "Erro ao consultar status.") as ApiError;
    error.status = res.status;
    throw error;
  }
  return res.json() as Promise<{ filename: string; status: IndexStatus; detail?: string }>;
}

async function apiAsk(query: string, token: string) {
  const form = new FormData();
  form.append("query", query);
  const res = await fetch(`${API_BASE}/chat/`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    const error: ApiError = new Error(text || "Erro ao consultar /chat.") as ApiError;
    error.status = res.status;
    throw error;
  }
  return res.json() as Promise<{ answer: string; sources?: Array<string | SourceMeta> }>;
}

const normalizeSources = (s?: Array<string | SourceMeta>): SourceMeta[] =>
  (s ?? []).map(x => (typeof x === "string" ? { source: x } : x));

const formatSourceLine = (src: SourceMeta) => {
  const filename = src.source?.split(/[\/]/).pop() || "documento";
  const page = typeof src.page === "number" ? `p.${src.page + 1}` : "p.?";
  return `${filename} - ${page}`;
};

const composeAnswer = (answer: string, sources: SourceMeta[]) => {
  const trimmed = answer.trim();
  if (!sources.length) return trimmed;
  const list = sources.map(s => `- ${formatSourceLine(s)}`).join("\n");
  return `${trimmed}\n\nFontes:\n${list}`;
};

function AuthView({
  mode,
  onModeChange,
  onSubmit,
  loading,
  error,
  email,
  password,
  onEmailChange,
  onPasswordChange,
}: {
  mode: "login" | "register";
  onModeChange: (mode: "login" | "register") => void;
  onSubmit: (e: FormEvent<HTMLFormElement>) => void;
  loading: boolean;
  error: string;
  email: string;
  password: string;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
}) {
  return (
    <div className="min-h-screen w-full bg-[var(--bg)] text-[var(--text)] flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-soft p-6 space-y-4">
        <div>
          <h1 className="text-2xl font-semibold">Portal RAG</h1>
          <p className="text-sm text-[var(--text-muted)]">Entre ou cadastre-se para acessar seus documentos.</p>
        </div>
        <div className="flex gap-2 text-sm">
          <button
            className={`px-3 py-1 rounded-lg border ${mode === "login" ? "bg-[var(--primary)] text-white" : "border-[var(--border)]"}`}
            onClick={() => onModeChange("login")}
            type="button"
          >
            Entrar
          </button>
          <button
            className={`px-3 py-1 rounded-lg border ${mode === "register" ? "bg-[var(--primary)] text-white" : "border-[var(--border)]"}`}
            onClick={() => onModeChange("register")}
            type="button"
          >
            Cadastrar
          </button>
        </div>
        {error && <div className="text-sm text-red-500">{error}</div>}
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">E-mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => onEmailChange(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Senha</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => onPasswordChange(e.target.value)}
              className="w-full px-3 py-2 rounded-xl border border-[var(--border)] bg-[var(--surface)] focus:outline-none focus:ring-2 focus:ring-[var(--primary)]"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full px-3 py-2 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-strong)] text-white font-medium shadow-soft disabled:opacity-60"
          >
            {loading ? "Enviando..." : mode === "login" ? "Entrar" : "Criar conta"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(STORAGE_TOKEN_KEY) ?? "");
  const [userEmail, setUserEmail] = useState<string>(() => localStorage.getItem(STORAGE_EMAIL_KEY) ?? "");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authEmail, setAuthEmail] = useState<string>(userEmail);
  const [authPassword, setAuthPassword] = useState<string>("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  const [file, setFile] = useState<File | null>(null);
  const [fileStatus, setFileStatus] = useState<IndexStatus | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileName = useMemo(() => file?.name ?? "", [file]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (!token || !fileName || fileStatus === "done" || fileStatus === "error") return;
    let timer: number | null = null;
    const poll = async () => {
      try {
        const r = await apiStatus(fileName, token);
        setFileStatus(r.status);
        if (r.status === "error" && r.detail) toast(`Erro na indexacao: ${r.detail.substring(0, 200)}`);
        if (r.status === "queued" || r.status === "processing") timer = window.setTimeout(poll, 1200);
      } catch (err) {
        const error = err as ApiError;
        if (error.status === 401) {
          handleLogout();
          toast("Sessao expirada. Faça login novamente.");
          return;
        }
        timer = window.setTimeout(poll, 1500);
      }
    };
    poll();
    return () => { if (timer) window.clearTimeout(timer); };
  }, [fileName, fileStatus, token]);

  const isAuthenticated = Boolean(token);

  const handleLogout = () => {
    setToken("");
    setUserEmail("");
    setAuthEmail("");
    localStorage.removeItem(STORAGE_TOKEN_KEY);
    localStorage.removeItem(STORAGE_EMAIL_KEY);
    setMessages([]);
    setFile(null);
    setFileStatus(null);
  };

  const handleAuthSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      const email = authEmail.trim().toLowerCase();
      const password = authPassword;
      if (authMode === "register") {
        await apiRegister(email, password);
      }
      const { access_token } = await apiLogin(email, password);
      setToken(access_token);
      setUserEmail(email);
      localStorage.setItem(STORAGE_TOKEN_KEY, access_token);
      localStorage.setItem(STORAGE_EMAIL_KEY, email);
      setAuthPassword("");
      setMessages([]);
      setFile(null);
      setFileStatus(null);
    } catch (err) {
      const error = err as ApiError;
      if (error.status === 401) {
        setAuthError("Credenciais inválidas.");
      } else {
        setAuthError(error.message || "Erro ao autenticar.");
      }
    } finally {
      setAuthLoading(false);
    }
  };

  async function handleUpload() {
    if (!file) return alert("Escolha um PDF primeiro");
    if (!token) return;
    setBusy(true);
    try {
      const r = await apiUpload(file, token);
      setFileStatus("queued");
      toast(r.message ?? "Arquivo recebido. Processando...");
    } catch (err) {
      const error = err as ApiError;
      if (error.status === 401) {
        handleLogout();
        toast("Sessao expirada. Faça login novamente.");
        return;
      }
      setFileStatus("error");
      toast(error.message || "Erro no upload");
    } finally {
      setBusy(false);
    }
  }

  async function handleAsk() {
    if (!question.trim() || !token) return;
    if (file && fileStatus !== "done") return toast("Aguarde concluir a indexacao.");
    const q = question;
    setMessages(prev => [...prev, { sender: "user", text: q }]);
    setQuestion("");
    setBusy(true);
    try {
      const r = await apiAsk(q, token);
      const sources = normalizeSources(r.sources);
      const answerWithSources = composeAnswer(r.answer ?? "-", sources);
      setMessages(prev => [...prev, { sender: "bot", text: answerWithSources }]);
    } catch (err) {
      const error = err as ApiError;
      if (error.status === 401) {
        handleLogout();
        toast("Sessao expirada. Faça login novamente.");
        return;
      }
      setMessages(prev => [...prev, { sender: "bot", text: "Falha ao buscar resposta." }]);
    } finally {
      setBusy(false);
    }
  }

  const handleKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  function toast(msg: string) {
    const el = document.createElement("div");
    el.className = "fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded-xl text-sm bg-[var(--text)] text-[var(--surface)] shadow-lg";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2200);
  }

  if (!isAuthenticated) {
    return (
      <AuthView
        mode={authMode}
        onModeChange={setAuthMode}
        onSubmit={handleAuthSubmit}
        loading={authLoading}
        error={authError}
        email={authEmail}
        password={authPassword}
        onEmailChange={setAuthEmail}
        onPasswordChange={setAuthPassword}
      />
    );
  }

  return (
    <div className="min-h-screen w-full bg-[var(--bg)] text-[var(--text)]">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <motion.header initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }} className="flex items-center gap-3 border-b border-[var(--border)] pb-4">
          <div className="w-10 h-10 grid place-items-center rounded-2xl bg-[var(--assistant-icon-bg)] text-[var(--assistant-icon-fg)] shadow-soft">
            <span className="text-lg">✦</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Portal RAG</h1>
            <p className="text-xs text-[var(--text-muted)]">Chat com PDFs locais</p>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-[var(--text-muted)]">
            <span>{userEmail}</span>
            <button onClick={handleLogout} className="px-3 py-1 rounded-lg border border-[var(--border)] hover:bg-[var(--surface-muted)]">Sair</button>
          </div>
        </motion.header>

        <motion.main initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.05 }} className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-soft p-5 mt-5 space-y-6">
          <section className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">Documentos</div>
                <div className="mt-1 text-sm text-[var(--text-muted)]">Uploads vinculados à sua conta.</div>
              </div>
            </div>
            <div className="mt-3 space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  type="file"
                  accept="application/pdf"
                  className="block w-full sm:w-auto file:mr-4 file:px-4 file:py-2 file:rounded-xl file:border file:border-[var(--border)] file:bg-[var(--surface)] file:text-[var(--text)] hover:file:bg-[var(--surface-muted)] file:cursor-pointer"
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setFile(f);
                    setFileStatus(f ? "idle" : null);
                  }}
                />
                <button
                  onClick={handleUpload}
                  disabled={!file || busy}
                  className="px-5 py-2 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-strong)] text-white font-medium shadow-soft disabled:opacity-50"
                >
                  {busy ? "Enviando..." : "Enviar PDF"}
                </button>
              </div>
              {file && (
                <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2">
                  <span className="text-sm font-medium text-[var(--text)] truncate max-w-full sm:max-w-[240px]">{file.name}</span>
                  {fileStatus && fileStatus !== "idle" && (
                    <span className="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium bg-[var(--chip-bg)] border border-[var(--chip-border)] text-[var(--text-muted)]">
                      status: {STATUS_LABEL[fileStatus] ?? fileStatus}
                    </span>
                  )}
                </div>
              )}
            </div>
          </section>

          <section className="bg-[var(--surface)] rounded-xl border border-[var(--border)]">
            <div ref={scrollRef} className="h-[420px] overflow-y-auto px-4 py-4 space-y-4 bg-[var(--surface-muted)] rounded-t-xl">
              {messages.length === 0 && (
                <div className="h-full grid place-items-center text-center text-[var(--text-muted)]">
                  Envie um PDF e faça uma pergunta.
                  <div className="text-xs mt-1">Ex.: "Quais são os tópicos principais?"</div>
                </div>
              )}

              {messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex ${m.sender === "user" ? "justify-end" : "items-start gap-3"}`}
                >
                  {m.sender === "bot" && (
                    <div className="w-9 h-9 rounded-full bg-[var(--assistant-icon-bg)] text-[var(--assistant-icon-fg)] grid place-items-center shadow-soft">AI</div>
                  )}
                  <div
                    className={`${m.sender === "user"
                      ? "bg-gradient-to-r from-[var(--primary)] to-[var(--primary-strong)] text-white ml-auto"
                      : "bg-[var(--surface)] border border-[var(--border)] text-[var(--text)]"} max-w-[80%] rounded-2xl px-4 py-3 shadow-sm whitespace-pre-wrap`}
                  >
                    {m.text}
                  </div>
                </motion.div>
              ))}
            </div>

            <div className="border-t border-[var(--border)] p-3 flex gap-3 bg-[var(--surface)] rounded-b-xl">
              <textarea
                rows={2}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={file && fileStatus !== "done" ? "Processando PDF..." : "Digite sua pergunta (Enter envia)"}
                disabled={busy || (file ? fileStatus !== "done" : false)}
                className="flex-1 resize-none bg-[var(--surface)] border border-[var(--border)] rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-[var(--primary)]"
              />
              <button
                onClick={handleAsk}
                disabled={busy || !question.trim() || (file ? fileStatus !== "done" : false)}
                className="px-5 py-2 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-strong)] text-[var(--text)] font-medium shadow-soft disabled:opacity-50"
              >
                {busy ? "Consultando..." : "Perguntar"}
              </button>
            </div>
          </section>
        </motion.main>

        <footer className="mt-6 text-center text-xs text-[var(--text-muted)]">Projeto baseado em FastAPI · LangChain · Chroma · Ollama</footer>
      </div>
    </div>
  );
}
