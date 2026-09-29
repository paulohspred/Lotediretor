import "server-only";
import { redirect } from "next/navigation";
import { authConfig } from "@/lib/auth/config";
import { NotAuthenticated, platformFetch } from "@/lib/auth/api";
import { getSession } from "@/lib/auth/session";

export type Membership = {
  org_id: string;
  name: string;
  kind: string;
  status: string;
  role: string;
};

export type Me = {
  user_id: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  memberships: Membership[];
  active_org: Membership;
};

export type Viewer =
  | { mode: "oidc"; me: Me }
  | { mode: "disabled"; me: null };

/**
 * For pages in the authenticated area: returns the account or redirects to
 * the login page, preserving where the user was going.
 */
export async function requireViewer(returnTo: string): Promise<Viewer> {
  const config = authConfig();
  if (config.mode !== "oidc") return { mode: "disabled", me: null };
  const session = await getSession();
  if (!session) {
    redirect(`/entrar?returnTo=${encodeURIComponent(returnTo)}`);
  }
  try {
    const response = await platformFetch("/me");
    if (response.status === 401) redirect(`/entrar?returnTo=${encodeURIComponent(returnTo)}`);
    if (!response.ok) throw new Error(`me ${response.status}`);
    return { mode: "oidc", me: (await response.json()) as Me };
  } catch (error) {
    if (error instanceof NotAuthenticated) {
      redirect(`/entrar?returnTo=${encodeURIComponent(returnTo)}`);
    }
    throw error;
  }
}

export async function apiJson<T>(path: string): Promise<T | null> {
  try {
    const response = await platformFetch(path);
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}
