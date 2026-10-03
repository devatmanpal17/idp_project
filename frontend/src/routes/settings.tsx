import { useEffect, useState, type ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Cpu, Database, RefreshCw, Save, Server } from "lucide-react";
import { Panel, PanelHeader } from "@/components/chaigaram/primitives";
import { checkAIHealth, updateAIConfig, type AIHealth } from "@/lib/ai-client";
import { apiJSON } from "@/lib/api";

type Diagnostics = {
  active_vectors: number;
  documents: Array<{
    document_id: string;
    counts: Record<string, number>;
    contiguous_watermark_ms: number;
  }>;
  cache: { entries: number; resident_bytes: number; max_bytes: number };
  query_vector_cache?: {
    entries: number;
    resident_bytes: number;
    max_bytes: number;
  };
  scheduler: {
    batch_size?: number;
    reason?: string;
    estimated_chunk_ms?: number;
  };
  metrics: Record<string, number>;
  jobs: Array<{
    id: string;
    operation: string;
    status: string;
    stage: string;
    resume_count: number;
  }>;
};

export const Route = createFileRoute("/settings")({
  head: () => ({ meta: [{ title: "Settings | ChaiGaram" }] }),
  component: SettingsScreen,
});

function SettingsScreen() {
  const [model, setModel] = useState("");
  const [health, setHealth] = useState<AIHealth | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);

  async function refresh() {
    try {
      setMessage(null);
      const [result, pipeline] = await Promise.all([
        checkAIHealth(),
        apiJSON<Diagnostics>("/vectors/diagnostics"),
      ]);
      setHealth(result);
      setDiagnostics(pipeline);
      const activeModel = result.llm_service?.model;
      if (typeof activeModel === "string") setModel(activeModel);
      return true;
    } catch (error) {
      setHealth(null);
      setDiagnostics(null);
      setMessage(
        error instanceof Error ? error.message : "Backend unavailable.",
      );
      return false;
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
      if (await refresh()) setMessage("Local model configuration updated.");
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Configuration failed.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-9">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">
            {import.meta.env["VITE_DEPLOY_TARGET"] === "render"
              ? "AI Settings"
              : "Local AI Settings"}
          </h1>
          <p className="text-xs text-muted-foreground">
            Only settings connected to a real backend service are shown.
          </p>
        </div>
        <button
          onClick={refresh}
          className="inline-flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs"
        >
          <RefreshCw className="h-4 w-4" /> Refresh
        </button>
      </div>

      <div className="grid gap-7 xl:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Ollama model"
            subtitle="Schema-validated, grounded quiz and tutor generation"
          />
          <div className="space-y-3 p-5">
            <label className="text-xs font-medium">Installed chat model</label>
            <div className="flex gap-2">
              <input
                value={model}
                onChange={(event) => setModel(event.target.value)}
                className="min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs"
              />
              <button
                onClick={save}
                disabled={saving || !model.trim()}
                className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-xs text-primary-foreground disabled:opacity-50"
              >
                <Save className="h-4 w-4" /> Save
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              The model must already exist in Ollama. Example:{" "}
              <code>ollama pull {model}</code>.
            </p>
          </div>
        </Panel>

        <Panel>
          <PanelHeader
            title="Live pipeline"
            subtitle="Values reported by FastAPI, Ollama, and ChromaDB"
          />
          <div className="divide-y divide-border p-5 text-xs">
            <StatusRow
              icon={<Server />}
              label="Backend"
              value={String(health?.status ?? "offline")}
            />
            <StatusRow
              icon={<Cpu />}
              label="Generation"
              value={
                health?.llm_service?.model_ready
                  ? String(health.active_ai_provider)
                  : "model unavailable"
              }
            />
            <StatusRow
              icon={<Database />}
              label="Embeddings"
              value={
                health?.embedding_service?.embedding_model_ready
                  ? String(health.embedding_service.embedding_model)
                  : "model unavailable"
              }
            />
            <StatusRow
              icon={<Database />}
              label="Chroma collection"
              value={`${String(health?.indexed_chunks ?? 0)} indexed chunks`}
            />
          </div>
        </Panel>
      </div>
      {diagnostics && (
        <Panel>
          <PanelHeader
            title="Capture and recovery"
            subtitle="Live observation gates, bounded retrieval cache, and durable jobs"
          />
          <div className="space-y-5 p-5 text-xs">
            <div className="grid gap-4 sm:grid-cols-3">
              <div>
                Searchable chunks
                <strong className="mt-1 block text-xl">
                  {diagnostics.active_vectors}
                </strong>
              </div>
              <div>
                Sealed chunks
                <strong className="mt-1 block text-xl">
                  {diagnostics.documents.reduce(
                    (sum, doc) => sum + (doc.counts["SEALED"] ?? 0),
                    0,
                  )}
                </strong>
              </div>
              <div>
                Cached payload
                <strong className="mt-1 block text-xl">
                  {(diagnostics.cache.resident_bytes / 1024).toFixed(1)} /{" "}
                  {(diagnostics.cache.max_bytes / 1024).toFixed(0)} KiB
                </strong>
              </div>
            </div>
            <p className="text-muted-foreground">
              Cache hits: {diagnostics.metrics["cache_hits"] ?? 0}. Embedding
              batches: {diagnostics.scheduler.batch_size ?? 0}. Scheduler:{" "}
              {diagnostics.scheduler.reason ?? "waiting for capture"}.
            </p>
            <p className="text-muted-foreground">
              The bounded retrieval cache gives priority to assessed topics with
              lower predicted recall; unassessed topics have neutral priority.
              Lower-priority admissions declined:{" "}
              {diagnostics.metrics["cache_priority_rejections"] ?? 0}. Cached
              query vectors: {diagnostics.query_vector_cache?.entries ?? 0}.
            </p>
            {diagnostics.documents.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      <th className="py-2">Video document</th>
                      <th>Observed from start</th>
                      <th>Pending chunks</th>
                      <th>Active</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diagnostics.documents.map((doc) => (
                      <tr
                        key={doc.document_id}
                        className="border-t border-border"
                      >
                        <td className="py-2 font-mono">
                          {doc.document_id.slice(0, 12)}
                        </td>
                        <td>
                          {(doc.contiguous_watermark_ms / 1000).toFixed(1)}s
                        </td>
                        <td>{doc.counts["UNEMBEDDED"] ?? 0}</td>
                        <td>{doc.counts["ACTIVE"] ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {diagnostics.jobs.length === 0 ? (
              <p className="text-muted-foreground">No AI jobs recorded yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr>
                      <th className="py-2">Recent operation</th>
                      <th>Status</th>
                      <th>Stage</th>
                      <th>Restarts</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diagnostics.jobs.slice(0, 10).map((job) => (
                      <tr key={job.id} className="border-t border-border">
                        <td className="py-2">{job.operation}</td>
                        <td>{job.status}</td>
                        <td>{job.stage}</td>
                        <td>{job.resume_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Panel>
      )}
      {message && (
        <div className="rounded-md border border-border bg-surface p-3 text-xs text-muted-foreground">
          {message}
        </div>
      )}
    </div>
  );
}

function StatusRow({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <span className="flex items-center gap-2 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="font-mono text-foreground">{value}</span>
    </div>
  );
}
