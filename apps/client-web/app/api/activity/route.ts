import { NextRequest } from "next/server";
import { authedProxy } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  return authedProxy(request, "/activity");
}
