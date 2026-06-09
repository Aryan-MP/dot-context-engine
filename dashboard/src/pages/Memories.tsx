import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";

const KIND_STYLES: Record<string, string> = {
  decision: "bg-emerald-900/60 text-emerald-300",
  rejected: "bg-rose-900/60 text-rose-300",
  action_item: "bg-amber-900/60 text-amber-300",
  note: "bg-zinc-800 text-zinc-300",
  conversation: "bg-sky-900/60 text-sky-300",
};

export default function Memories() {
  const [search, setSearch] = useState("");
  const queryClient = useQueryClient();
  const memories = useQuery({
    queryKey: ["memories", search],
    queryFn: () => api.memories(search ? `&query=${encodeURIComponent(search)}` : ""),
  });

  const items = memories.data?.memories ?? [];

  return (
    <div className="space-y-4">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Memory timeline</h1>
          <p className="text-sm text-zinc-500">every captured decision, searchable</p>
        </div>
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="semantic search…"
          className="w-72 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
      </header>

      {items.length === 0 && (
        <p className="py-12 text-center text-zinc-500">no memories{search ? " match" : " yet"}</p>
      )}

      <ol className="relative space-y-3 border-l border-zinc-800 pl-5">
        {items.map((memory) => (
          <li key={memory.id} className="relative">
            <span className="absolute -left-[26px] top-2 h-2.5 w-2.5 rounded-full bg-emerald-500" />
            <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="mb-1 flex items-center gap-2 text-xs">
                <span className={`rounded-full px-2 py-0.5 ${KIND_STYLES[memory.kind] ?? KIND_STYLES.note}`}>
                  {memory.kind}
                </span>
                <span className="text-zinc-500">{memory.source}</span>
                {memory.file_path && (
                  <span className="font-mono text-zinc-500">{memory.file_path}</span>
                )}
                <span className="ml-auto text-zinc-600">
                  {memory.created_at?.slice(0, 10)} · weight {memory.weight.toFixed(2)}
                </span>
                <button
                  onClick={() =>
                    api.deleteMemory(memory.id).then(() =>
                      queryClient.invalidateQueries({ queryKey: ["memories"] })
                    )
                  }
                  className="text-zinc-600 hover:text-rose-400"
                  title="forget"
                >
                  ✕
                </button>
              </div>
              <p className="whitespace-pre-wrap text-sm text-zinc-200">{memory.content}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
