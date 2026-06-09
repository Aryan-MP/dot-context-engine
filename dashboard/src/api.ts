// The daemon serves the built dashboard from the same origin, so relative
// URLs work in production; the vite dev server proxies them (vite.config.ts).

export interface Status {
  project: string;
  project_root: string;
  files_indexed: number;
  chunks: number;
  memories: number;
  last_indexed: string | null;
  embedding_backend: string;
  vector_backend: string;
  git_branch?: string | null;
  uptime_seconds?: number;
}

export interface Memory {
  id: string;
  kind: string;
  content: string;
  source: string;
  file_path: string;
  tags: string[];
  confidence: number;
  weight: number;
  created_at: string | null;
}

export interface GraphNode {
  id: string;
  language: string;
  edit_count: number;
  last_modified: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  internal: boolean;
}

export interface ContextChunk {
  file_path: string;
  symbol: string;
  kind: string;
  start_line: number;
  end_line: number;
  language: string;
  content: string;
  score: number;
  score_components: Record<string, number>;
}

export interface ContextResult {
  query: string;
  tokens_used: number;
  token_budget: number;
  assembly_ms: number;
  chunks: ContextChunk[];
  decisions: Memory[];
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

export const api = {
  status: () => get<Status>("/status"),
  memories: (params = "") => get<{ memories: Memory[] }>(`/memory?limit=200${params}`),
  graph: () => get<{ nodes: GraphNode[]; edges: GraphEdge[] }>("/graph"),
  context: (query: string, file?: string) => {
    const search = new URLSearchParams({ query, fmt: "raw" });
    if (file) search.set("file", file);
    return get<ContextResult>(`/context?${search}`);
  },
  deleteMemory: (id: string) => fetch(`/memory/${id}`, { method: "DELETE" }),
  sync: () =>
    fetch("/sync", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ force: false }),
    }),
};
