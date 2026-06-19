"use client";

import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { OntologyGraphWorkspace } from "./OntologyGraphWorkspace";

export default function GraphPage() {
  return (
    <WorkflowPageShell workflowId="ontology">
      <OntologyGraphWorkspace />
    </WorkflowPageShell>
  );
}
