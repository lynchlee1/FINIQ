import type { ReactNode } from "react";
import { WorkflowSidebar } from "./WorkflowSidebar";
import type { SidebarDefinition, WorkflowTab } from "./types";

type WorkflowPageShellProps = {
  sidebar?: SidebarDefinition;
  tabs?: WorkflowTab[];
  children: ReactNode;
  defaultSidebarTitle?: string;
  defaultGroupLabel?: string;
};

export function WorkflowPageShell({
  sidebar,
  tabs = [],
  children,
  defaultSidebarTitle = "작업 메뉴",
  defaultGroupLabel = "Workflow",
}: WorkflowPageShellProps) {
  const resolvedSidebar = sidebar ?? {
    title: defaultSidebarTitle,
    groups: [{ label: defaultGroupLabel, steps: tabs }],
  };
  const hasSidebar = resolvedSidebar.groups.some((group) => group.steps.length > 0);

  return (
    <main className={hasSidebar ? "grid w-full gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start" : "flex w-full flex-col gap-6"}>
      {hasSidebar ? <WorkflowSidebar title={resolvedSidebar.title} groups={resolvedSidebar.groups} /> : null}
      <div className="min-w-0 flex flex-col gap-6">{children}</div>
    </main>
  );
}
