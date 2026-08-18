import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/simulator")({
  head: () => ({
    meta: [
      { title: "Extension Simulator | Cognivue" },
      { name: "description", content: "Simulate the Cognivue extension experience" },
    ]
  }),
  component: Simulator,
});

function Simulator() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-semibold tracking-tight">Extension Simulator</h1>
        <p className="text-muted-foreground">Test how the extension behaves on different pages.</p>
      </div>
      <div className="panel p-6">
        <p className="text-muted-foreground">Simulator controls and output will appear here.</p>
      </div>
    </div>
  );
}
