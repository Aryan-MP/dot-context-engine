import * as vscode from "vscode";

export interface DotChunk {
  file_path: string;
  symbol: string;
  kind: string;
  start_line: number;
  end_line: number;
  language: string;
  content: string;
  score: number;
}

export interface DotDecision {
  id: string;
  kind: string;
  content: string;
  source: string;
  file_path: string;
  created_at: string | null;
  weight: number;
}

export interface DotContext {
  query: string;
  current_file: string | null;
  token_budget: number;
  tokens_used: number;
  assembly_ms: number;
  chunks: DotChunk[];
  decisions: DotDecision[];
}

export interface DotStatus {
  project: string;
  files_indexed: number;
  chunks: number;
  memories: number;
  last_indexed: string | null;
}

function baseUrl(): string {
  return vscode.workspace
    .getConfiguration("dot")
    .get<string>("apiUrl", "http://127.0.0.1:7337")
    .replace(/\/$/, "");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(baseUrl() + path, {
    ...init,
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) {
    throw new Error(`Dot API ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

export class DotApi {
  async status(): Promise<DotStatus> {
    return request<DotStatus>("/status");
  }

  async isUp(): Promise<boolean> {
    try {
      await this.status();
      return true;
    } catch {
      return false;
    }
  }

  async context(query: string, file?: string, tokenBudget?: number): Promise<DotContext> {
    const params = new URLSearchParams({ query, fmt: "raw" });
    if (file) params.set("file", file);
    if (tokenBudget) params.set("token_budget", String(tokenBudget));
    return request<DotContext>(`/context?${params}`);
  }

  async contextFormatted(query: string, file: string | undefined, fmt: string): Promise<string> {
    const params = new URLSearchParams({ query, fmt });
    if (file) params.set("file", file);
    const response = await fetch(`${baseUrl()}/context?${params}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error(`Dot API ${response.status}`);
    return await response.text();
  }

  async captureMemory(content: string, kind: string, filePath: string): Promise<void> {
    await request("/memory", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content, kind, file_path: filePath, source: "vscode" }),
    });
  }

  async sync(): Promise<void> {
    await request("/sync", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ force: false }),
    });
  }
}
