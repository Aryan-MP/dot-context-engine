import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, ContextResult } from "../api";

export default function ContextPreview() {
  const [query, setQuery] = useState("");
  const [file, setFile] = useState("");
  const preview = useMutation<ContextResult, Error>({
    mutationFn: () => api.context(query, file || undefined),
  });

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Context preview</h1>
        <p className="text-sm text-zinc-500">
          see exactly what Dot would inject for any query — scores and all
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          preview.mutate();
        }}
        className="flex gap-3"
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="what would you ask an AI tool?"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <input
          value={file}
          onChange={(event) => setFile(event.target.value)}
          placeholder="current file (optional)"
          className="w-64 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm outline-none focus:border-emerald-500"
        />
        <button
          type="submit"
          disabled={preview.isPending}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          Assemble
        </button>
      </form>

      {preview.data && (
        <div className="space-y-3">
          <p className="text-xs text-zinc-500">
            {preview.data.tokens_used}/{preview.data.token_budget} tokens ·
            assembled in {preview.data.assembly_ms.toFixed(1)}ms ·
            {preview.data.chunks.length} chunks · {preview.data.decisions.length} decisions
          </p>

          {preview.data.decisions.map((decision) => (
            <div key={decision.id} className="rounded-xl border border-emerald-900/60 bg-emerald-950/30 p-3 text-sm">
              <span className="mr-2 text-xs font-medium uppercase text-emerald-400">{decision.kind}</span>
              {decision.content}
            </div>
          ))}

          {preview.data.chunks.map((chunk, index) => (
            <details key={index} className="rounded-xl border border-zinc-800 bg-zinc-900/60">
              <summary className="cursor-pointer px-4 py-2 text-sm">
                <span className="font-mono text-zinc-300">
                  {chunk.file_path}:{chunk.start_line}-{chunk.end_line}
                </span>
                <span className="ml-2 text-zinc-500">{chunk.symbol}</span>
                <span className="float-right text-xs text-emerald-400">
                  score {chunk.score.toFixed(3)}
                </span>
              </summary>
              <div className="border-t border-zinc-800 p-4">
                <div className="mb-2 flex gap-3 text-xs text-zinc-500">
                  {Object.entries(chunk.score_components).map(([name, value]) => (
                    <span key={name}>
                      {name}: <span className="text-zinc-300">{value.toFixed(2)}</span>
                    </span>
                  ))}
                </div>
                <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300">
                  {chunk.content}
                </pre>
              </div>
            </details>
          ))}
        </div>
      )}
      {preview.isError && (
        <p className="text-sm text-rose-400">failed: {preview.error.message}</p>
      )}
    </div>
  );
}
