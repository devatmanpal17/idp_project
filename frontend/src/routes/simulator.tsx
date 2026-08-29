import { useEffect, useState, type ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { CheckCircle2, Database, RefreshCw, Server, ShieldCheck } from "lucide-react";
import { Panel, PanelHeader } from "@/components/chaigaram/primitives";
import { checkAIHealth, fetchIndexedTopics, type AIHealth } from "@/lib/ai-client";

export const Route = createFileRoute("/simulator")({
  head: () => ({
    meta: [
      { title: "Browser Extension | ChaiGaram" },
      { name: "description", content: "Install and inspect the live ChaiGaram browser extension" },
    ],
  }),
  component: ExtensionScreen,
});

function ExtensionScreen() {
  const [health, setHealth] = useState<AIHealth | null>(null);
  const [topics, setTopics] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setError(null);
    try {
      const [nextHealth, nextTopics] = await Promise.all([checkAIHealth(), fetchIndexedTopics()]);
      setHealth(nextHealth);
      setTopics(nextTopics);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reach the local AI backend.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="space-y-9">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">Browser Learning Extension</h1>
          <p className="text-xs text-muted-foreground">
            Turns any article, documentation page, course, or video into a private study space.
          </p>
        </div>
        <button onClick={refresh} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs">
          <RefreshCw className="h-4 w-4" /> Refresh live status
        </button>
      </div>

      {error && <div className="rounded-md border border-warn/40 bg-warn/10 p-3 text-xs text-warn">{error}</div>}

      <div className="grid gap-5 md:grid-cols-3">
        <StatusCard icon={<Server />} label="FastAPI" value={String(health?.status ?? "offline")} ready={health?.status === "ready"} />
        <StatusCard icon={<Database />} label="Chroma chunks" value={String(health?.indexed_chunks ?? 0)} ready={Boolean(health)} />
        <StatusCard icon={<ShieldCheck />} label="Local model" value={String(health?.active_ai_provider ?? "unavailable")} ready={Boolean(health?.llm_service?.model_ready)} />
      </div>

      <Panel>
        <PanelHeader title="Install in Chrome or Edge" subtitle="Load the unpacked Manifest V3 extension directly from this project." />
        <ol className="list-decimal space-y-3 p-6 pl-10 text-sm text-muted-foreground">
          <li>Open <code className="text-foreground">chrome://extensions</code> or <code className="text-foreground">edge://extensions</code>.</li>
          <li>Enable Developer mode and select <strong className="text-foreground">Load unpacked</strong>.</li>
          <li>Select <code className="text-foreground">chaigaram/extension</code>.</li>
          <li>Open any HTTP or HTTPS lesson page, then click the ChaiGaram toolbar icon.</li>
          <li>Use visible captions, save a selection, or choose <strong>Learn this page</strong>.</li>
        </ol>
      </Panel>

      <Panel>
        <PanelHeader title="Live indexed topics" subtitle={`${topics.length} topic${topics.length === 1 ? "" : "s"} derived from extension captures`} />
        {topics.length ? (
          <div className="flex flex-wrap gap-2 p-5">
            {topics.map((topic) => <span key={topic} className="rounded-full border border-border bg-surface-2 px-3 py-1 text-xs">{topic}</span>)}
          </div>
        ) : (
          <div className="p-8 text-center text-xs text-muted-foreground">No captured lessons yet. The dashboard remains empty until the extension indexes real content.</div>
        )}
      </Panel>
    </div>
  );
}

function StatusCard({ icon, label, value, ready }: { icon: ReactNode; label: string; value: string; ready: boolean }) {
  return (
    <Panel className="p-4">
      <div className="flex items-center gap-2 text-muted-foreground">{icon}<span className="text-xs font-semibold">{label}</span></div>
      <div className="mt-3 flex items-center gap-2 text-sm font-semibold text-foreground">
        {ready && <CheckCircle2 className="h-4 w-4 text-positive" />}{value}
      </div>
    </Panel>
  );
}
