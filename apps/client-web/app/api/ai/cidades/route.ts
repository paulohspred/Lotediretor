import { NextRequest, NextResponse } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  if (!body) return NextResponse.json({ code: "INVALID_JSON" }, { status: 400 });
  // Forward only known fields.
  const payload = {
    ibge_code: body.ibge_code,
    question: body.question,
    zone_code: body.zone_code,
  };
  return authedProxy(request, "/ai/cidades/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    timeoutMs: 90_000,
  });
}
