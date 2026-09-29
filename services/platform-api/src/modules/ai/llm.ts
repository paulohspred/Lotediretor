/**
 * Minimal Anthropic Messages API client (fetch, no SDK) with forced tool use
 * for schema-shaped output. Model and endpoint are configuration, so the
 * provider can be swapped or pointed at a gateway (Blueprint §30.3/§30.24).
 */
export type LlmConfig = {
  apiKey: string;
  baseUrl: string;
  model: string;
  maxTokens: number;
  timeoutMs: number;
};

export function llmConfigFromEnv(): LlmConfig | null {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;
  return {
    apiKey,
    baseUrl: (process.env.AI_BASE_URL ?? "https://api.anthropic.com").replace(/\/$/, ""),
    model: process.env.AI_MODEL ?? "claude-sonnet-5-5",
    maxTokens: Number(process.env.AI_MAX_TOKENS ?? 1500),
    timeoutMs: Number(process.env.AI_TIMEOUT_MS ?? 60_000),
  };
}

export type ToolSpec = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
};

export type ToolCallResult<T> = {
  input: T;
  model: string;
  inputTokens: number | null;
  outputTokens: number | null;
};

export class LlmError extends Error {
  constructor(message: string, readonly retryable: boolean) {
    super(message);
  }
}

export async function callTool<T>(
  config: LlmConfig,
  system: string,
  userContent: string,
  tool: ToolSpec,
): Promise<ToolCallResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${config.baseUrl}/v1/messages`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": config.apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: config.model,
        max_tokens: config.maxTokens,
        temperature: 0,
        system,
        tools: [tool],
        tool_choice: { type: "tool", name: tool.name },
        messages: [{ role: "user", content: userContent }],
      }),
      signal: AbortSignal.timeout(config.timeoutMs),
    });
  } catch {
    throw new LlmError("LLM request failed", true);
  }
  const body = (await response.json().catch(() => ({}))) as {
    model?: string;
    content?: Array<{ type: string; name?: string; input?: unknown }>;
    usage?: { input_tokens?: number; output_tokens?: number };
  };
  if (!response.ok) {
    throw new LlmError(`LLM HTTP ${response.status}`, response.status >= 500 || response.status === 429);
  }
  const call = body.content?.find((c) => c.type === "tool_use" && c.name === tool.name);
  if (!call || typeof call.input !== "object" || call.input === null) {
    throw new LlmError("LLM returned no structured answer", false);
  }
  return {
    input: call.input as T,
    model: body.model ?? config.model,
    inputTokens: body.usage?.input_tokens ?? null,
    outputTokens: body.usage?.output_tokens ?? null,
  };
}
