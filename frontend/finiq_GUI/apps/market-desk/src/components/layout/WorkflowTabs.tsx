"use client"

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";

interface Tab {
  href: string;
  step: number;
  label: string;
}

interface WorkflowTabsProps {
  tabs: Tab[];
}

export function WorkflowTabs({ tabs }: WorkflowTabsProps) {
  const pathname = usePathname();

  return (
    <nav className="bg-white dark:bg-[#161b22] rounded-xl shadow-sm border border-slate-200 dark:border-[#30363d] p-1 flex gap-1 mb-6 transition-colors" aria-label="Workflow steps">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex-1 flex items-center justify-center gap-3 py-3 px-4 rounded-lg transition-all",
              isActive 
                ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 shadow-md" 
                : "text-slate-500 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-[#21262d] hover:text-slate-900 dark:hover:text-slate-100"
            )}
          >
            <span className={cn(
              "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border",
              isActive 
                ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100 border-white dark:border-slate-800" 
                : "bg-slate-100 dark:bg-[#0d1117] text-slate-500 dark:text-slate-500 border-slate-200 dark:border-[#30363d]"
            )}>
              {tab.step}
            </span>
            <span className="font-medium text-sm">{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
