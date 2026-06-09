import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import ForceGraph from "../components/ForceGraph";

export default function Graph() {
  const graph = useQuery({ queryKey: ["graph"], queryFn: api.graph, refetchInterval: 60_000 });

  if (graph.isLoading) return <p className="text-zinc-500">loading graph…</p>;
  if (graph.isError || !graph.data)
    return <p className="text-zinc-500">graph unavailable — is the daemon running?</p>;

  const { nodes, edges } = graph.data;
  const internal = edges.filter((edge) => edge.internal).length;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Dependency graph</h1>
        <p className="text-sm text-zinc-500">
          {nodes.length} files · {internal} internal edges · node size = edit frequency
        </p>
      </header>
      <ForceGraph nodes={nodes} edges={edges} />
    </div>
  );
}
