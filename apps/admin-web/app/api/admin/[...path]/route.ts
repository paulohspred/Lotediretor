import { NextRequest, NextResponse } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ path: string[] }> };

// Only /admin/* on the platform API is reachable through this BFF.
const SEGMENT = /^[A-Za-z0-9_-]{1,64}$/;

async function forward(request: NextRequest, context: Ctx, method: string) {
  const { path } = await context.params;
  if (!path.length || !path.every((s) => SEGMENT.test(s))) {
    return NextResponse.json({ code: "NOT_FOUND" }, { status: 404 });
  }
  const target = `/admin/${path.join("/")}${request.nextUrl.search}`;
  if (method === "GET") return authedProxy(request, target);
  const body = await request.json().catch(() => ({}));
  return authedProxy(request, target, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const GET = (r: NextRequest, c: Ctx) => forward(r, c, "GET");
export const POST = (r: NextRequest, c: Ctx) => forward(r, c, "POST");
export const PATCH = (r: NextRequest, c: Ctx) => forward(r, c, "PATCH");
