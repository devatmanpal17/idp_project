import { useEffect, useState, type ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Cpu, Database, RefreshCw, Save, Server } from "lucide-react";
import { Panel, PanelHeader } from "@/components/chaigaram/primitives";
import { checkAIHealth, updateAIConfig, type AIHealth } from "@/lib/ai-client";

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings | ChaiGaram" }] }),
  component: SettingsScreen,
});

function SettingsScreen() {
  const [model, setModel] = useState("");
  const [health, setHealth] = useState<AIHealth | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      const result = await checkAIHealth();
      setHealth(result);
      const activeModel = result.llm_service?.model;
      if (typeof activeModel === "string") setModel(activeModel);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Backend unavailable.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      await updateAIConfig({ provider: "ollama", model });
      await refresh();
      setMessage("Local model configuration updated.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Configuration failed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-9">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">Local AI Settings</h1>
          <p className="text-xs text-muted-foreground">Only settings connected to a real backend service are shown.</p>
        </div>
        <button onClick={refresh} className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs"><RefreshCw className="h-4 w-4" /> Refresh</button>
      </div>

      <div className="grid gap-7 xl:grid-cols-2">
        <Panel>
          <PanelHeader title="Ollama model" subtitle="Schema-validated, grounded quiz and tutor generation" />
          <div className="space-y-3 p-5">
            <label className="text-xs font-medium">Installed chat model</label>
            <div className="flex gap-2">
              <input value={model} onChange={(event) => setModel(event.target.value)} className="min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs" />
              <button onClick={save} disabled={saving || !model.trim()} className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs text-primary-foreground disabled:opacity-50"><Save className="h-4 w-4" /> Save</button>
            </div>
            <p className="text-[11px] text-muted-foreground">The model must already exist in Ollama. Example: <code>ollama pull {model}</code>.</p>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Live pipeline" subtitle="Values reported by FastAPI, Ollama, and ChromaDB" />
          <div className="divide-y divide-border p-5 text-xs">
            <StatusRow icon={<Server />} label="Backend" value={String(health?.status ?? "offline")} />
            <StatusRow icon={<Cpu />} label="Generation" value={health?.llm_service?.model_ready ? String(health.active_ai_provider) : "model unavailable"} />
            <StatusRow icon={<Database />} label="Embeddings" value={health?.embedding_service?.embedding_model_ready ? String(health.embedding_service.embedding_model) : "model unavailable"} />
            <StatusRow icon={<Database />} label="Chroma collection" value={`${String(health?.indexed_chunks ?? 0)} indexed chunks`} />
          </div>
        </Panel>
      </div>
      {message && <div className="rounded-md border border-border bg-surface p-3 text-xs text-muted-foreground">{message}</div>}
    </div>
  );
}

function StatusRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 py-3"><span className="flex items-center gap-2 text-muted-foreground">{icon}{label}</span><span className="font-mono text-foreground">{value}</span></div>;
}
