"use client"

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";
import type { WorkflowTab } from "@/config/navigation";

interface WorkflowTabsProps {
  tabs: WorkflowTab[];
}

export function WorkflowTabs({ tabs }: WorkflowTabsProps) {
  const pathname = usePathname();

  return (
    <nav className="overflow-x-auto rounded-2xl border border-slate-200/80 bg-white/85 p-1 shadow-[0_18px_45px_-34px_rgba(15,23,42,0.55)] backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-900/85" aria-label="Workflow steps">
      <div className="flex min-w-max gap-1 lg:min-w-0">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex min-w-[132px] flex-1 items-center justify-center gap-3 rounded-xl px-4 py-3 transition-all",
                isActive 
                  ? "bg-slate-950 text-white shadow-sm dark:bg-slate-100 dark:text-slate-950"
                  : "text-slate-500 hover:bg-slate-100/80 hover:text-slate-950 dark:text-slate-500 dark:hover:bg-slate-800/75 dark:hover:text-slate-100"
            )}
          >
            <span className={cn(
              "flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-semibold",
              isActive 
                ? "border-white bg-white text-slate-950 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                : "border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-500"
            )}>
              {tab.step}
            </span>
            <span className="font-medium text-sm">{tab.label}</span>
          </Link>
        );
      })}
      </div>
    </nav>
  );
}
