import { NextRequest, NextResponse } from "next/server";

const AGENT_URL = process.env.AGENT_URL || "";
const AGENT_API_KEY = process.env.AGENT_API_KEY || "";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  if (!AGENT_URL) {
    return NextResponse.json(
      { error: "AGENT_URL not configured" },
      { status: 500 }
    );
  }

  const { path } = await params;
  const pathStr = path.join("/");
  const url = `${AGENT_URL.replace(/\/$/, "")}/${pathStr}`;

  try {
    const body = await request.text();
    const contentType = request.headers.get("content-type") || "application/json";

    const headers: Record<string, string> = { "Content-Type": contentType };
    if (AGENT_API_KEY) {
      headers["X-API-Key"] = AGENT_API_KEY;
    }

    const res = await fetch(url, {
      method: "POST",
      headers,
      body: body || undefined,
    });

    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("[api/agent] proxy error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Proxy request failed" },
      { status: 502 }
    );
  }
}
