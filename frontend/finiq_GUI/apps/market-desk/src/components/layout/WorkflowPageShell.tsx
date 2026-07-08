import type { ReactNode } from "react";
import { WorkflowPageShell as WebAppWorkflowPageShell } from "@finiq/web-app";
import { getSidebarDefinition, getWorkflowTabs, type WorkflowId, type WorkflowTab } from "@/config/navigation";

type WorkflowPageShellProps = {
  workflowId?: WorkflowId;
  tabs?: WorkflowTab[];
  children: ReactNode;
};

export function WorkflowPageShell({ workflowId, tabs, children }: WorkflowPageShellProps) {
  const resolvedTabs = tabs ?? (workflowId ? getWorkflowTabs(workflowId) : []);
  const sidebar = workflowId ? getSidebarDefinition(workflowId) : { title: "작업 메뉴", groups: [{ label: "Workflow", steps: resolvedTabs }] };

  return (
    <WebAppWorkflowPageShell sidebar={sidebar} tabs={resolvedTabs}>
      {children}
    </WebAppWorkflowPageShell>
  );
}
