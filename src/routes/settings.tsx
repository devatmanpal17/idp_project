import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings | Cognivue" },
      { name: "description", content: "Configure your Cognivue experience" },
    ]
  }),
  component: Settings,
});

function Settings() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Manage your account and preferences.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Settings options will appear here.</p>
      </div>
    </div>
  );
}
