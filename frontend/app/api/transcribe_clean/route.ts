import { NextRequest } from "next/server";

export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const language = searchParams.get("language") || "mn";
  const vad = searchParams.get("vad") || "true";

  const formData = await req.formData();

  // FastAPI backend URL (root дээр асах портоо тааруулна)
  const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";

  const res = await fetch(`${backendUrl}/transcribe_clean?language=${language}&vad=${vad}`, {
    method: "POST",
    body: formData,
  });

  const data = await res.text();
  return new Response(data, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") || "application/json" },
  });
}