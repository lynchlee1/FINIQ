import { WorkflowPageShell } from "@/components/layout/WorkflowPageShell";
import { OntologyChartWorkspace } from "./OntologyChartWorkspace";

export default function GraphChartPage() {
  return (
    <WorkflowPageShell workflowId="ontology">
      <OntologyChartWorkspace />
    </WorkflowPageShell>
  );
}
