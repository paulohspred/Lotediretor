import { NextRequest, NextResponse } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UUID = /^[0-9a-f-]{36}$/i;

type Ctx = { params: Promise<{ id: string }> };

export async function PATCH(request: NextRequest, context: Ctx) {
  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  const body = await request.json().catch(() => null);
  return authedProxy(request, `/properties/${id}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
}

export async function DELETE(request: NextRequest, context: Ctx) {
  const { id } = await context.params;
  if (!UUID.test(id)) return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  return authedProxy(request, `/properties/${id}`, { method: "DELETE" });
}
