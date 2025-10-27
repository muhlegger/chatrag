import React, { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";

type SourceMeta = { source: string; page?: number };
type Msg = { sender: "user" | "bot"; text: string; sources?: SourceMeta[] };

const API_BASE = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function apiUpload(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/upload/`, { method: "POST", body: form });
  if (!res.ok) throw new Error("Upload failed");
  return res.json() as Promise<{ status: string; message: string }>;
}
async function apiStatus(filename: string) {
  const res = await fetch(`${API_BASE}/index-status/${encodeURIComponent(filename)}`);
  if (!res.ok) throw new Error("Status not found");
  return res.json() as Promise<{ filename: string; status: "queued" | "processing" | "done" | "error"; detail?: string }>;
}
async function apiAsk(query: string) {
  const form = new FormData();
  form.append("query", query);
  const res = await fetch(`${API_BASE}/chat/`, { method: "POST", body: form });
  if (!res.ok) throw new Error("/chat request failed");
  return res.json() as Promise<{ answer: string; sources?: Array<string | SourceMeta> }>;
}
const normalizeSources = (s?: Array<string | SourceMeta>): SourceMeta[] =>
  (s ?? []).map(x => (typeof x === "string" ? { source: x } : x));

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full px-3 py-1 text-xs font-medium bg-[var(--chip-bg)] border border-[var(--chip-border)] text-[var(--text-muted)]">
      {children}
    </span>
  );
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="text-xs uppercase tracking-[0.2em] text-[var(--text-muted)]">{children}</div>;
}
const formatSourceLine = (src: SourceMeta) => {
  const filename = src.source?.split(/[\\\\/]/).pop() || "document";
  const page = typeof src.page === "number" ? `p.${src.page + 1}` : "p.?";
  return `${filename} – ${page}`;
};

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [fileStatus, setFileStatus] = useState<null | "idle" | "queued" | "processing" | "done" | "error">(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileName = useMemo(() => file?.name ?? "", [file]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    let timer: number | null = null;
    if (!fileName || fileStatus === "done" || fileStatus === "error") return;
    const poll = async () => {
      try {
        const r = await apiStatus(fileName);
        setFileStatus(r.status);
        if (r.status === "error" && r.detail) toast(`Index error: ${r.detail.substring(0, 200)}`);
        if (r.status === "queued" || r.status === "processing") timer = window.setTimeout(poll, 1200);
      } catch { timer = window.setTimeout(poll, 1500); }
    };
    if (fileStatus === "queued" || fileStatus === "processing") poll();
    return () => { if (timer) window.clearTimeout(timer); };
  }, [fileName, fileStatus]);

  async function handleUpload() {
    if (!file) return alert("Choose a PDF first");
    setBusy(true);
    try {
      const r = await apiUpload(file);
      setFileStatus("queued");
      toast(r.message ?? "File received. Processing...");
    } catch {
      setFileStatus("error");
      toast("Upload error");
    } finally { setBusy(false); }
  }
  async function handleAsk() {
    if (!question.trim()) return;
    if (file && fileStatus !== "done") return toast("Please wait for indexing to finish.");
    const q = question;
    setMessages(prev => [...prev, { sender: "user", text: q }]);
    setQuestion(""); setBusy(true);
    try {
      const r = await apiAsk(q);
      setMessages(prev => [...prev, { sender: "bot", text: r.answer ?? "-", sources: normalizeSources(r.sources) }]);
    } catch {
      setMessages(prev => [...prev, { sender: "bot", text: "Request failed." }]);
    } finally { setBusy(false); }
  }
  const handleKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk(); }
  };

  function toast(msg: string) {
    const el = document.createElement("div");
    el.className = "fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded-xl text-sm bg-[var(--text)] text-[var(--surface)] shadow-lg";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2200);
  }

  return (
    <div className="min-h-screen w-full bg-[var(--bg)] text-[var(--text)]">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <motion.header initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .35 }} className="flex items-center gap-3 border-b border-[var(--border)] pb-4">
          <div className="w-10 h-10 grid place-items-center rounded-2xl bg-[var(--assistant-icon-bg)] text-[var(--assistant-icon-fg)] shadow-soft">
            <span className="text-lg">?</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Portal RAG</h1>
            <p className="text-xs text-[var(--text-muted)]">Conversas com documentos</p>
          </div>
          <div className="ml-auto text-xs text-[var(--text-muted)]">API: <code className="text-[var(--text)]">{API_BASE}</code></div>
        </motion.header>

        <motion.main initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4, delay: .05 }} className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-soft p-5 mt-5 space-y-6">
          <section className="bg-[var(--surface)] rounded-xl border border-[var(--border)] p-4">
            <SectionTitle>Documentos</SectionTitle>
            <div className="mt-3 space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row">
                <input type="file" accept="application/pdf" className="block w-full sm:w-auto file:mr-4 file:px-4 file:py-2 file:rounded-xl file:border file:border-[var(--border)] file:bg-[var(--surface)] file:text-[var(--text)] hover:file:bg-[var(--surface-muted)] file:cursor-pointer" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); setFileStatus(f ? "idle" : null); }} />
                <button onClick={handleUpload} disabled={!file || busy} className="px-5 py-2 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-strong)] text-white font-medium shadow-soft disabled:opacity-50">{busy ? "Uploading..." : "Upload PDF"}</button>
              </div>
              {file && (
                <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-2">
                  <span className="text-sm font-medium text-[var(--text)] truncate max-w-full sm:max-w-[240px]">{file.name}</span>
                  {fileStatus && <Chip>status: {fileStatus}</Chip>}
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

              {messages.map((m, i) => {
                if (m.sender === "user") {
                  return (
                    <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
                      <div className="bg-gradient-to-r from-[var(--primary)] to-[var(--primary-strong)] text-white max-w-[80%] rounded-2xl px-4 py-3 shadow-sm">
                        <div className="whitespace-pre-wrap">{m.text}</div>
                      </div>
                    </motion.div>
                  );
                }
                return (
                  <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex items-start gap-3">
                    <div className="w-9 h-9 rounded-full bg-[var(--assistant-icon-bg)] text-[var(--assistant-icon-fg)] grid place-items-center shadow-soft">??</div>
                    <div className="bg-[var(--surface)] border border-[var(--border)] text-[var(--text)] max-w-[80%] rounded-2xl px-4 py-3 shadow-sm">
                      <div className="whitespace-pre-wrap">{m.text}</div>
                      {m.sources?.length ? (
                        <div className="mt-3 space-y-1 text-xs text-[var(--text-muted)]">
                          {m.sources.map((s, idx) => (
                            <div key={idx} className="flex flex-wrap gap-1">
                              <span className="font-medium text-[var(--text)]">Source {idx + 1}:</span>
                              <span>{formatSourceLine(s)}</span>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  </motion.div>
                );
              })}
            </div>

            <div className="border-t border-[var(--border)] p-3 flex gap-3 bg-[var(--surface)] rounded-b-xl">
              <textarea rows={2} value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={handleKeyDown} placeholder={file && fileStatus !== "done" ? "Aguarde o processamento do PDF..." : "Digite sua pergunta (Enter para enviar)"} disabled={busy || (file ? fileStatus !== "done" : false)} className="flex-1 resize-none bg-[var(--surface)] border border-[var(--border)] rounded-xl px-3 py-2 outline-none focus:ring-2 focus:ring-[var(--primary)]" />
              <button onClick={handleAsk} disabled={busy || !question.trim() || (file ? fileStatus !== "done" : false)} className="px-5 py-2 rounded-xl bg-[var(--accent)] hover:bg-[var(--accent-strong)] text-[var(--text)] font-medium shadow-soft disabled:opacity-50">{busy ? "Consultando..." : "Perguntar"}</button>
            </div>
          </section>
        </motion.main>

        <footer className="mt-6 text-center text-xs text-[var(--text-muted)]">Construído com FastAPI · LangChain · Chroma · Ollama</footer>
      </div>
    </div>
  );
}

