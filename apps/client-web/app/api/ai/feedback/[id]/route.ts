import { NextRequest, NextResponse } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  const body = (await request.json().catch(() => null)) as { value?: unknown } | null;
  return authedProxy(request, `/ai/cidades/traces/${id}/feedback`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ value: body?.value }),
  });
}
