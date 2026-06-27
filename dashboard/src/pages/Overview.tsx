import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import StatCard from "../components/StatCard";

export default function Overview() {
  const status = useQuery({ queryKey: ["status"], queryFn: api.status });
  const memories = useQuery({ queryKey: ["memories"], queryFn: () => api.memories() });

  if (status.isError) {
    return (
      <div className="rounded-xl border border-amber-700/50 bg-amber-950/30 p-6 text-amber-200">
        Can't reach the Dot daemon. Start it with <code className="font-mono">dot daemon start</code>.
      </div>
    );
  }
  const data = status.data;

  // memories captured per day, last 14 days
  const byDay = new Map<string, number>();
  for (const memory of memories.data?.memories ?? []) {
    if (!memory.created_at) continue;
    const day = memory.created_at.slice(0, 10);
    byDay.set(day, (byDay.get(day) ?? 0) + 1);
  }
  const series = [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([day, count]) => ({ day: day.slice(5), count }));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">{data?.project ?? "…"}</h1>
        <p className="text-sm text-zinc-500">{data?.project_root}</p>
      </header>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Files indexed" value={data?.files_indexed ?? "—"} />
        <StatCard label="Code chunks" value={data?.chunks ?? "—"} />
        <StatCard label="Memories" value={data?.memories ?? "—"} />
        <StatCard
          label="Last sync"
          value={data?.last_indexed ? new Date(data.last_indexed + "Z").toLocaleTimeString() : "never"}
          hint={data?.git_branch ? `branch: ${data.git_branch}` : undefined}
        />
      </div>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
        <h2 className="mb-3 text-sm font-medium text-zinc-400">Decisions captured (last 14 days)</h2>
        {series.length ? (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={series}>
              <XAxis dataKey="day" stroke="#71717a" fontSize={11} />
              <YAxis stroke="#71717a" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
              />
              <Bar dataKey="count" fill="#34d399" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="py-8 text-center text-sm text-zinc-500">
            No memories yet — they accrue from commits, comments, and captures.
          </p>
        )}
      </section>

      <section className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm">
        <div className="space-y-1 text-zinc-400">
          <div>embeddings: <span className="text-zinc-200">{data?.embedding_backend}</span></div>
          <div>vector store: <span className="text-zinc-200">{data?.vector_backend}</span></div>
        </div>
        <button
          onClick={() => api.sync().then(() => status.refetch())}
          className="rounded-lg bg-emerald-600 px-4 py-2 font-medium text-white hover:bg-emerald-500"
        >
          Re-index project
        </button>
      </section>
    </div>
  );
}
