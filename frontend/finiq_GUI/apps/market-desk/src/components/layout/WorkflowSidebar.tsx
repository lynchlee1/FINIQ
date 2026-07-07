"use client"

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";
import type { SidebarGroup, WorkflowTab } from "@/config/navigation";

type WorkflowSidebarProps = {
  title: string;
  tabs?: WorkflowTab[];
  groups?: SidebarGroup[];
};

export function WorkflowSidebar({ title, tabs = [], groups }: WorkflowSidebarProps) {
  const pathname = usePathname();
  const resolvedGroups = groups ?? [{ label: "Workflow", steps: tabs }];

  return (
    <aside className="w-full min-w-0 self-start rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors dark:bg-[#161b22] dark:border-[#30363d]">
      <nav className="space-y-5" aria-label={title}>
        {resolvedGroups.map((group) => (
          <div key={group.label} className="space-y-1">
            <h3 className="px-3 pb-1 text-base font-bold text-slate-900 dark:text-slate-100">{group.label}</h3>
            {group.steps.map((tab) => {
              const isActive = pathname === tab.href;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={cn(
                    "flex items-center rounded-lg pl-6 pr-3 py-2.5 text-[13px] font-medium transition-colors",
                    isActive
                      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-[#21262d] dark:hover:text-slate-100"
                  )}
                >
                  <span className="min-w-0 truncate">{tab.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
