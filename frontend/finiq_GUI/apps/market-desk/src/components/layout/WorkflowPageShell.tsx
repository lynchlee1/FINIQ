import type { ReactNode } from "react";
import { getSidebarDefinition, getWorkflowTabs, type WorkflowId, type WorkflowTab } from "@/config/navigation";
import { WorkflowSidebar } from "./WorkflowSidebar";

type WorkflowPageShellProps = {
  workflowId?: WorkflowId;
  tabs?: WorkflowTab[];
  children: ReactNode;
};

export function WorkflowPageShell({ workflowId, tabs, children }: WorkflowPageShellProps) {
  const resolvedTabs = tabs ?? (workflowId ? getWorkflowTabs(workflowId) : []);
  const sidebar = workflowId ? getSidebarDefinition(workflowId) : { title: "작업 메뉴", groups: [{ label: "Workflow", steps: resolvedTabs }] };

  return (
    <main className={resolvedTabs.length ? "grid w-full gap-6 lg:grid-cols-[220px_minmax(0,1fr)]" : "flex w-full flex-col gap-6"}>
      {resolvedTabs.length ? <WorkflowSidebar title={sidebar.title} groups={sidebar.groups} /> : null}
      <div className="min-w-0 flex flex-col gap-6">{children}</div>
    </main>
  );
}
