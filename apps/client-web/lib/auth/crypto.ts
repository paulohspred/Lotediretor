import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

/**
 * Authenticated encryption for data the BFF stores (session tokens) or hands
 * to the browser (short-lived login state). AES-256-GCM with a random IV.
 */
export function keyFromSecret(secret: string): Buffer {
  const raw = Buffer.from(secret, "base64");
  if (raw.length < 32) {
    throw new Error("SESSION_SECRET must be at least 32 bytes, base64-encoded");
  }
  return createHash("sha256").update(raw).digest();
}

export function seal(key: Buffer, value: unknown, aad: string): Buffer {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  cipher.setAAD(Buffer.from(aad));
  const body = Buffer.concat([
    cipher.update(Buffer.from(JSON.stringify(value), "utf8")),
    cipher.final(),
  ]);
  return Buffer.concat([iv, cipher.getAuthTag(), body]);
}

export function open<T>(key: Buffer, sealed: Buffer, aad: string): T | null {
  if (sealed.length < 29) return null;
  try {
    const decipher = createDecipheriv("aes-256-gcm", key, sealed.subarray(0, 12));
    decipher.setAAD(Buffer.from(aad));
    decipher.setAuthTag(sealed.subarray(12, 28));
    const text = Buffer.concat([
      decipher.update(sealed.subarray(28)),
      decipher.final(),
    ]).toString("utf8");
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export function sealToString(key: Buffer, value: unknown, aad: string): string {
  return seal(key, value, aad).toString("base64url");
}

export function openFromString<T>(key: Buffer, text: string | undefined, aad: string): T | null {
  if (!text) return null;
  return open<T>(key, Buffer.from(text, "base64url"), aad);
}

export function newSessionId(): string {
  return randomBytes(32).toString("base64url");
}

export function sessionHash(id: string): string {
  return createHash("sha256").update(id).digest("hex");
}

/** Only same-app relative paths are allowed as post-login destinations. */
export function safeReturnTo(value: string | null | undefined, fallback = "/dashboard"): string {
  if (!value || typeof value !== "string") return fallback;
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return fallback;
  }
  if (/[\r\n]/.test(value) || value.length > 512) return fallback;
  if (value.startsWith("/auth/")) return fallback;
  return value;
}
