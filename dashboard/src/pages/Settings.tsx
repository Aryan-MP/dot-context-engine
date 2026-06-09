import { useQuery } from "@tanstack/react-query";
import { api } from "../api";

export default function Settings() {
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const data = status.data;

  const rows: [string, string][] = [
    ["Project root", data?.project_root ?? "—"],
    ["Embedding backend", data?.embedding_backend ?? "—"],
    ["Vector backend", data?.vector_backend ?? "—"],
    ["Git branch", data?.git_branch ?? "—"],
    [
      "Daemon uptime",
      data?.uptime_seconds != null ? `${Math.round(data.uptime_seconds / 60)} min` : "—",
    ],
  ];

  return (
    <div className="max-w-2xl space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-zinc-500">
          runtime configuration lives in <code className="font-mono">.dot/config.json</code> in
          your project — edit it and restart the daemon
        </p>
      </header>

      <div className="divide-y divide-zinc-800 rounded-xl border border-zinc-800 bg-zinc-900/60">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between px-4 py-3 text-sm">
            <span className="text-zinc-400">{label}</span>
            <span className="font-mono text-zinc-200">{value}</span>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-400">
        <h2 className="mb-2 font-medium text-zinc-200">Tunable keys in .dot/config.json</h2>
        <ul className="list-inside list-disc space-y-1 font-mono text-xs">
          <li>token_budget — default context size (4000)</li>
          <li>recency_half_life_hours — how fast code recency fades (72)</li>
          <li>memory_half_life_days — forgetting-curve half-life (30)</li>
          <li>embedding_model — sentence-transformers model name</li>
          <li>profiles — quick-assist / deep-dive context presets</li>
          <li>extra_ignored_dirs — additional paths to skip indexing</li>
        </ul>
      </div>
    </div>
  );
}
