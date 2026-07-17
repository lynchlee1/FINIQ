"use client";

import { AppFrame as WebAppFrame } from "@finiq/web-app/layout";
import { WorkflowSidebar } from "@finiq/web-app/workflow";
import { usePathname } from "next/navigation";
import { getActiveNavItem, getSidebarDefinition } from "@/config/navigation";
import { Topbar } from "./Topbar";

type AppFrameProps = {
  children: React.ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  const pathname = usePathname();
  const activeItem = getActiveNavItem(pathname);
  const isDisclosureWorkflow = activeItem?.workflowId === "disclosure-build";
  const sidebar = getSidebarDefinition("disclosure-build");

  return (
    <WebAppFrame topbar={<Topbar />}>
      {isDisclosureWorkflow ? (
        <main
          className="grid w-full gap-6 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start"
          data-testid="persistent-disclosure-layout"
        >
          <WorkflowSidebar title={sidebar.title} groups={sidebar.groups} />
          <div className="min-w-0 flex flex-col gap-6">{children}</div>
        </main>
      ) : children}
    </WebAppFrame>
  );
}
