import { NextResponse } from "next/server";

const PLATFORM_API_URL =
  process.env.PLATFORM_API_URL ?? "http://127.0.0.1:3000";

/**
 * Server-side GET to the platform API. The browser never talks to the API
 * directly (BFF pattern, Blueprint §32.8). The status and error body from the
 * API are passed through so the UI can show precise messages.
 */
export async function proxyGet(
  path: string,
  params?: URLSearchParams,
  timeoutMs = 10_000,
): Promise<NextResponse> {
  const query = params && [...params.keys()].length ? `?${params}` : "";
  try {
    const response = await fetch(`${PLATFORM_API_URL}${path}${query}`, {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({}));
    return NextResponse.json(body, {
      status: response.status,
      headers: { "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      {
        code: "PLATFORM_API_UNAVAILABLE",
        message: "Serviço temporariamente indisponível.",
        retryable: true,
      },
      { status: 502 },
    );
  }
}
