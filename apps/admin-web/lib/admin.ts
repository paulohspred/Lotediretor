import "server-only";
import { redirect } from "next/navigation";
import { authConfig } from "@/lib/auth/config";
import { NotAuthenticated, platformFetch } from "@/lib/auth/api";
import { getSession } from "@/lib/auth/session";

export type AdminMe = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  mfa: boolean;
};

export type AdminGate =
  | { ok: true; me: AdminMe }
  | { ok: false; reason: "role" | "mfa"; me: AdminMe };

const ADMIN_ROLE = process.env.ADMIN_ROLE ?? "platform-admin";

/** Session + platform-admin role + MFA, or a reason to show the gate page. */
export async function requireAdmin(): Promise<AdminGate> {
  const config = authConfig();
  if (config.app !== "admin") {
    throw new Error("admin-web must run with AUTH_APP=admin (separate cookies and client)");
  }
  if (config.mode !== "oidc") {
    throw new Error("O painel admin não funciona com AUTH_MODE=disabled");
  }
  if (!(await getSession())) redirect("/entrar");
  let response: Response;
  try {
    response = await platformFetch("/me");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/entrar");
    throw error;
  }
  if (response.status === 401) redirect("/entrar");
  const me = (await response.json()) as AdminMe;
  if (!me.roles?.includes(ADMIN_ROLE)) return { ok: false, reason: "role", me };
  if (!me.mfa) return { ok: false, reason: "mfa", me };
  return { ok: true, me };
}

export async function adminJson<T>(path: string): Promise<T | null> {
  try {
    const response = await platformFetch(`/admin${path}`);
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
