import { NextRequest } from "next/server";
import { proxyGet } from "@/lib/platform";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const params = new URLSearchParams({
    lat: request.nextUrl.searchParams.get("lat") ?? "",
    lng: request.nextUrl.searchParams.get("lng") ?? "",
  });
  return proxyGet("/municipalities/resolve", params);
}
