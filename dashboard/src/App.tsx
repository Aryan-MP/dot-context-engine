import { useState } from "react";
import ContextPreview from "./pages/ContextPreview";
import Graph from "./pages/Graph";
import Memories from "./pages/Memories";
import Overview from "./pages/Overview";
import Settings from "./pages/Settings";

const PAGES = {
  overview: { label: "Overview", component: Overview },
  graph: { label: "Dependency graph", component: Graph },
  memories: { label: "Memories", component: Memories },
  context: { label: "Context preview", component: ContextPreview },
  settings: { label: "Settings", component: Settings },
} as const;

type PageKey = keyof typeof PAGES;

export default function App() {
  const [page, setPage] = useState<PageKey>("overview");
  const Page = PAGES[page].component;

  return (
    <div className="flex min-h-screen">
      <nav className="w-52 shrink-0 border-r border-zinc-800 p-4">
        <div className="mb-6 flex items-center gap-2">
          <span className="inline-block h-3 w-3 rounded-full bg-emerald-400" />
          <span className="text-lg font-semibold tracking-tight">dot</span>
        </div>
        <ul className="space-y-1">
          {(Object.keys(PAGES) as PageKey[]).map((key) => (
            <li key={key}>
              <button
                onClick={() => setPage(key)}
                className={`w-full rounded-md px-3 py-1.5 text-left text-sm transition ${
                  page === key
                    ? "bg-zinc-800 text-zinc-50"
                    : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"
                }`}
              >
                {PAGES[key].label}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <main className="flex-1 overflow-x-hidden p-6">
        <Page />
      </main>
    </div>
  );
}
