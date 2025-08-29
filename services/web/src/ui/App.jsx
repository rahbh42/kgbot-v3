import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";

// If you're still bypassing Traefik for testing, set to "http://localhost:8088"
const apiBase = ""; // same-origin via Traefik

const tokenKey = "token";
const convKey  = "conversation_id";

function useBearer() {
  const [token, setToken] = useState(localStorage.getItem(tokenKey) || "");
  useEffect(() => { localStorage.setItem(tokenKey, token || ""); }, [token]);
  const headers = useMemo(() => token ? { Authorization: `Bearer ${token}` } : {}, [token]);
  return { token, setToken, headers };
}

function useConversation() {
  const [conversationId, setConversationId] = useState(localStorage.getItem(convKey) || "");
  useEffect(() => { if (conversationId) localStorage.setItem(convKey, conversationId); }, [conversationId]);
  return { conversationId, setConversationId };
}

function Button({ children, ...props }) {
  return (
    <button
      {...props}
      style={{
        padding: "8px 12px",
        borderRadius: 10,
        border: "1px solid #ddd",
        background: "#111",
        color: "#fff",
        cursor: "pointer",
        ...props.style
      }}
    >
      {children}
    </button>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: "block", marginBottom: 10 }}>
      <div style={{ fontSize: 12, opacity: 0.7, marginBottom: 6 }}>{label}</div>
      {children}
    </label>
  );
}

function Tabs({ tab, setTab }) {
  const tabs = ["Chat", "Graph", "Admin"];
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
      {tabs.map(t => (
        <button key={t}
          onClick={() => setTab(t)}
          style={{
            padding: "8px 12px",
            borderRadius: 10,
            border: "1px solid #ddd",
            background: t === tab ? "#111" : "#fff",
            color: t === tab ? "#fff" : "#111",
            cursor: "pointer"
          }}
        >{t}</button>
      ))}
    </div>
  );
}

function Health({ headers }) {
  const [health, setHealth] = useState("...");
  useEffect(() => {
    let aborted = false;
    axios.get(`${apiBase}/api/health`, { headers }).then(() => {
      if (!aborted) setHealth("OK");
    }).catch(() => {
      if (!aborted) setHealth("FAILED");
    });
    return () => { aborted = true; };
  }, [headers]);
  return <div>Health: <b>{health}</b></div>;
}

function Chat({ headers, conversationId, setConversationId }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [docInfo, setDocInfo] = useState(null);
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [sources, setSources] = useState([]);
  const [thinking, setThinking] = useState(false);
  const inputRef = useRef(null);

  async function doUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const { data } = await axios.post(`${apiBase}/api/upload`, form, { headers });
      setDocInfo(data);
    } catch (e) {
      alert(`Upload failed: ${e?.response?.status} – ${e?.response?.data?.detail || e.message}`);
    } finally {
      setUploading(false);
    }
  }

  async function ask() {
    if (!q.trim()) return;
    setThinking(true);
    try {
      const payload = { question: q, top_k: 8 };
      if (conversationId) payload.conversation_id = conversationId;
      const { data } = await axios.post(`${apiBase}/api/chat`, payload, { headers });
      setAnswer(data.answer || "");
      setSources(data.sources || []);
      if (!conversationId && data.conversation_id) setConversationId(data.conversation_id);
    } catch (e) {
      console.error(e);
      alert(`Ask failed: ${e?.response?.status} – ${e?.response?.data?.detail || e.message}`);
    } finally {
      setThinking(false);
    }
  }

  function clearChat() {
    setAnswer("");
    setSources([]);
    setQ("");
    // keep conversationId so follow-ups continue to have memory
    inputRef.current?.focus();
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Bearer token">
          <div style={{ opacity: 0.7, fontSize: 13 }}>Set it above in the header section.</div>
        </Field>
        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ fontSize: 12, opacity: 0.7 }}>Conversation</div>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={conversationId}
              onChange={e => setConversationId(e.target.value)}
              placeholder="(auto-created on first ask)"
              style={{ flex: 1, padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
            />
            <Button onClick={() => { localStorage.removeItem("conversation_id"); setConversationId(""); }}>
              New
            </Button>
          </div>
        </div>
      </div>

      <div style={{ padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10 }}>
          <input type="file" onChange={e => setFile(e.target.files?.[0] || null)} />
          <Button onClick={doUpload} disabled={!file || uploading}>{uploading ? "Uploading..." : "Upload"}</Button>
          {docInfo ? <span style={{ fontSize: 12, opacity: 0.7 }}>doc_id: {docInfo.doc_id}</span> : null}
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <textarea
            ref={inputRef}
            rows={3}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Ask a question..."
            style={{ width: "100%", padding: 8, borderRadius: 8, border: "1px solid #ddd", fontFamily: "inherit" }}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <Button onClick={ask} disabled={thinking}>{thinking ? "Thinking…" : "Ask"}</Button>
            <Button onClick={clearChat} style={{ background: "#fff", color: "#111" }}>Clear</Button>
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center", marginLeft: "auto" }}>
              <input type="checkbox" checked={sourcesOpen} onChange={e => setSourcesOpen(e.target.checked)} />
              Show sources
            </label>
          </div>
        </div>

        <div style={{ marginTop: 14, padding: 12, borderRadius: 10, background: "#fafafa", minHeight: 60 }}>
          {thinking ? <em>Thinking…</em> : (answer || <span style={{ opacity: 0.6 }}>No answer yet.</span>)}
        </div>

        {sourcesOpen && sources?.length > 0 && (
          <details open style={{ marginTop: 10 }}>
            <summary>Sources / Context ({sources.length})</summary>
            <ul>
              {sources.map((s, i) => (
                <li key={i} style={{ marginBottom: 8 }}>
                  <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", background: "#fff", padding: 8, borderRadius: 8, border: "1px solid #eee" }}>
                    {s.text || JSON.stringify(s)}
                  </pre>
                  {"score" in s ? <div style={{ fontSize: 12, opacity: 0.6 }}>score: {s.score}</div> : null}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  );
}

function Graph({ headers }) {
  const [triples, setTriples] = useState([]);
  const [limit, setLimit] = useState(100);
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const { data } = await axios.get(`${apiBase}/api/graph/triples?limit=${limit}`, { headers });
      setTriples(data.triples || []);
    } catch (e) {
      alert(`Browse failed: ${e?.response?.status} – ${e?.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); /* on mount */ }, []); // eslint-disable-line

  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <Field label="Limit">
          <input type="number" value={limit} min={1} max={1000}
                 onChange={e => setLimit(parseInt(e.target.value || "100", 10))}
                 style={{ width: 120, padding: 8, borderRadius: 8, border: "1px solid #ddd" }} />
        </Field>
        <Button onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</Button>
      </div>
      <div style={{ border: "1px solid #eee", borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ background: "#f4f4f4" }}>
              <th style={{ textAlign: "left", padding: 8 }}>Subject</th>
              <th style={{ textAlign: "left", padding: 8 }}>Predicate</th>
              <th style={{ textAlign: "left", padding: 8 }}>Object</th>
            </tr>
          </thead>
          <tbody>
            {triples.map((t, i) => (
              <tr key={i} style={{ borderTop: "1px solid #eee" }}>
                <td style={{ padding: 8 }}>{t.s}</td>
                <td style={{ padding: 8 }}>{t.p}</td>
                <td style={{ padding: 8 }}>{t.o}</td>
              </tr>
            ))}
            {triples.length === 0 && (
              <tr><td colSpan={3} style={{ padding: 12, opacity: 0.6 }}>No triples.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Admin({ headers }) {
  const [busy, setBusy] = useState(false);
  async function clearKG() {
    if (!confirm("Clear the entire knowledge graph and embeddings?")) return;
    setBusy(true);
    try {
      const { data } = await axios.post(`${apiBase}/api/graph/clear`, null, { headers });
      alert(data && data.ok ? "Cleared." : "Done.");
    } catch (e) {
      alert(`Clear failed: ${e?.response?.status} – ${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <Button onClick={clearKG} disabled={busy} style={{ background: "#b00020" }}>
        {busy ? "Clearing…" : "Clear Knowledge Graph"}
      </Button>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        This drops all RDF triples and deletes the Qdrant collection (it will be re-created on next ingest).
      </div>
    </div>
  );
}

export default function App() {
  const { token, setToken, headers } = useBearer();
  const { conversationId, setConversationId } = useConversation();
  const [tab, setTab] = useState("Chat");

  return (
    <div style={{ fontFamily: "Inter, system-ui, Arial", maxWidth: 1000, margin: "24px auto", padding: "0 12px" }}>
      <h1 style={{ marginBottom: 8 }}>KG Chatbot</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
        <Field label="Bearer token">
          <input
            placeholder="super-secret-token"
            value={token}
            onChange={e => setToken(e.target.value)}
            style={{ width: 320, padding: 8, borderRadius: 8, border: "1px solid #ddd" }}
          />
        </Field>
        <Health headers={headers} />
      </div>

      <Tabs tab={tab} setTab={setTab} />

      {tab === "Chat"   && <Chat headers={headers} conversationId={conversationId} setConversationId={setConversationId} />}
      {tab === "Graph"  && <Graph headers={headers} />}
      {tab === "Admin"  && <Admin headers={headers} />}
    </div>
  );
}
