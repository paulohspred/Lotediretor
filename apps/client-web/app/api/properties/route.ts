import { NextRequest, NextResponse } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  return authedProxy(request, "/properties");
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ code: "INVALID_JSON" }, { status: 400 });
  }
  return authedProxy(request, "/properties", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}
