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
    <nav className="overflow-x-auto rounded-xl border border-slate-200 bg-white p-1 shadow-sm transition-colors dark:bg-[#161b22] dark:border-[#30363d]" aria-label="Workflow steps">
      <div className="flex min-w-max gap-1 lg:min-w-0">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "flex min-w-[132px] flex-1 items-center justify-center gap-3 rounded-lg px-4 py-3 transition-all",
                isActive 
                  ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 shadow-md" 
                  : "text-slate-500 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-[#21262d] hover:text-slate-900 dark:hover:text-slate-100"
            )}
          >
            <span className={cn(
              "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border",
              isActive 
                ? "bg-white dark:bg-[#161b22] text-slate-900 dark:text-slate-100 border-white dark:border-[#30363d]" 
                : "bg-slate-100 dark:bg-[#0d1117] text-slate-500 dark:text-slate-500 border-slate-200 dark:border-[#30363d]"
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
