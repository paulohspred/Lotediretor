import { NextRequest, NextResponse } from "next/server";
import { NotAuthenticated, platformFetch } from "@/lib/auth/api";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) {
    return NextResponse.json({ code: "INVALID_ID" }, { status: 400 });
  }
  try {
    const response = await platformFetch(`/reports/properties/${id}.pdf`, {
      timeoutMs: 120_000,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ code: "REPORT_FAILED" }));
      return NextResponse.json(body, { status: response.status });
    }
    return new NextResponse(await response.arrayBuffer(), {
      status: 200,
      headers: {
        "content-type": "application/pdf",
        "content-disposition":
          response.headers.get("content-disposition") ??
          `attachment; filename="lotediretor-${id}.pdf"`,
        "cache-control": "private, no-store",
      },
    });
  } catch (error) {
    if (error instanceof NotAuthenticated) {
      return NextResponse.json(
        { code: "AUTH_REQUIRED", message: "Sua sessão expirou. Entre novamente." },
        { status: 401 },
      );
    }
    return NextResponse.json(
      { code: "REPORT_UNAVAILABLE", message: "Relatório temporariamente indisponível." },
      { status: 502 },
    );
  }
}
