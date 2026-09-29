import * as oidc from "openid-client";
import { authConfig, type AuthConfig } from "./config";

let cached: { key: string; config: Promise<oidc.Configuration> } | null = null;

export function oidcConfiguration(config: AuthConfig = authConfig()): Promise<oidc.Configuration> {
  const key = `${config.issuer}|${config.clientId}`;
  if (!cached || cached.key !== key) {
    const execute = config.allowInsecureIssuer ? [oidc.allowInsecureRequests] : [];
    const promise = oidc.discovery(
      new URL(config.issuer),
      config.clientId,
      config.clientSecret,
      undefined,
      { execute },
    );
    // Do not cache a failed discovery (IdP briefly down at boot).
    promise.catch(() => {
      if (cached?.key === key) cached = null;
    });
    cached = { key, config: promise };
  }
  return cached.config;
}

export type LoginState = {
  state: string;
  nonce: string;
  verifier: string;
  returnTo: string;
  createdAt: number;
};

export async function beginLogin(returnTo: string, extra: Record<string, string> = {}) {
  const config = authConfig();
  const server = await oidcConfiguration(config);
  const verifier = oidc.randomPKCECodeVerifier();
  const state: LoginState = {
    state: oidc.randomState(),
    nonce: oidc.randomNonce(),
    verifier,
    returnTo,
    createdAt: Date.now(),
  };
  const url = oidc.buildAuthorizationUrl(server, {
    redirect_uri: new URL("/auth/callback", config.baseUrl).toString(),
    scope: config.scopes,
    code_challenge: await oidc.calculatePKCECodeChallenge(verifier),
    code_challenge_method: "S256",
    state: state.state,
    nonce: state.nonce,
    ...extra,
  });
  return { url, state };
}

export async function completeLogin(callbackUrl: URL, login: LoginState) {
  const server = await oidcConfiguration();
  return oidc.authorizationCodeGrant(server, callbackUrl, {
    pkceCodeVerifier: login.verifier,
    expectedState: login.state,
    expectedNonce: login.nonce,
    idTokenExpected: true,
  });
}

export async function refresh(refreshToken: string) {
  return oidc.refreshTokenGrant(await oidcConfiguration(), refreshToken);
}

export async function endSessionUrl(idToken: string | undefined): Promise<string | null> {
  const config = authConfig();
  const server = await oidcConfiguration(config);
  if (!server.serverMetadata().end_session_endpoint) return null;
  return oidc
    .buildEndSessionUrl(server, {
      post_logout_redirect_uri: new URL("/", config.baseUrl).toString(),
      ...(idToken ? { id_token_hint: idToken } : { client_id: config.clientId }),
    })
    .toString();
}
