import { NextRequest, NextResponse } from "next/server";
import { proxyGet } from "@/lib/platform";

export const runtime = "nodejs";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ ibge: string }> },
) {
  const { ibge } = await context.params;
  if (!/^\d{7}$/.test(ibge)) {
    return NextResponse.json(
      { code: "INVALID_IBGE_CODE", message: "Código IBGE inválido." },
      { status: 400 },
    );
  }
  return proxyGet(`/municipalities/${ibge}/coverage`);
}
