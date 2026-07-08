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
    <aside className="w-full min-w-0 self-start rounded-2xl border border-slate-200/80 bg-white/85 p-3 shadow-[0_18px_45px_-34px_rgba(15,23,42,0.55)] backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-900/85 lg:sticky lg:top-7">
      <nav className="space-y-5" aria-label={title}>
        {resolvedGroups.map((group) => (
          <div key={group.label} className="space-y-1">
            <h3 className="px-3 pb-2 text-[11px] font-semibold tracking-[0.16em] text-slate-500 dark:text-slate-400">{group.label}</h3>
            {group.steps.map((tab) => {
              const isActive = pathname === tab.href;
              return (
                <Link
                  key={tab.href}
                  href={tab.href}
                  className={cn(
                    "flex min-h-10 items-center rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all",
                    isActive
                      ? "bg-slate-950 text-white shadow-sm dark:bg-slate-100 dark:text-slate-950"
                      : "text-slate-600 hover:bg-slate-100/80 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800/75 dark:hover:text-slate-100"
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
