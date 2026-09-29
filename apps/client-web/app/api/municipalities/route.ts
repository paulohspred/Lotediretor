import { NextRequest, NextResponse } from "next/server";
import { proxyGet } from "@/lib/platform";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const q = request.nextUrl.searchParams.get("q")?.trim() ?? "";
  const uf = request.nextUrl.searchParams.get("uf")?.trim() ?? "";
  if (q.length < 2 || q.length > 80) {
    return NextResponse.json({ results: [] });
  }
  const params = new URLSearchParams({ q, limit: "10" });
  if (/^[A-Za-z]{2}$/.test(uf)) params.set("uf", uf.toUpperCase());
  return proxyGet("/municipalities", params);
}
