"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [vad, setVad] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const form = new FormData();
      form.append("file", file);

      // Next -> FastAPI proxy (дараа нь 4-р алхамд тохируулна)
      const res = await fetch(`/api/transcribe_clean?language=mn&vad=${vad}`, {
        method: "POST",
        body: form,
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data?.error || "Request failed");

      setResult(data);
    } catch (e: any) {
      setError(e.message || "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 860, margin: "40px auto", padding: 16, fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 28, fontWeight: 700 }}>MN-ASR Web Upload</h1>
      <p style={{ opacity: 0.8 }}>MP3/WAV/MP4 файл оруулаад хөрвүүлнэ.</p>

      <div style={{ marginTop: 20, padding: 16, border: "1px solid #ddd", borderRadius: 12 }}>
        <input
          type="file"
          accept="audio/*,video/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        <div style={{ marginTop: 12 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={vad} onChange={(e) => setVad(e.target.checked)} />
            VAD (чимээг таслах)
          </label>
        </div>

        <button
          onClick={onSubmit}
          disabled={!file || loading}
          style={{
            marginTop: 12,
            padding: "10px 14px",
            borderRadius: 10,
            border: "1px solid #333",
            background: loading ? "#eee" : "#111",
            color: loading ? "#111" : "#fff",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "Хөрвүүлж байна..." : "Transcribe"}
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 20, color: "crimson" }}>
          <b>Error:</b> {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 20 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700 }}>Result</h2>

          <div style={{ padding: 14, border: "1px solid #ddd", borderRadius: 12, marginTop: 8 }}>
            <div><b>Language:</b> {result.language}</div>
            <div><b>Duration:</b> {result.duration}s</div>

            <h3 style={{ marginTop: 12 }}>Text</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{result.text}</p>

            {result.text_raw && (
              <>
                <h3 style={{ marginTop: 12 }}>Raw</h3>
                <p style={{ whiteSpace: "pre-wrap", opacity: 0.85 }}>{result.text_raw}</p>
              </>
            )}

            <h3 style={{ marginTop: 12 }}>Segments</h3>
            <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(result.segments, null, 2)}</pre>
          </div>
        </div>
      )}
    </main>
  );
}