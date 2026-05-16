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
    <nav className="bg-white dark:bg-[#131722] rounded-xl shadow-sm border border-slate-200 dark:border-[#2a2e39] p-1 flex gap-1 mb-6 transition-colors" aria-label="Workflow steps">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex-1 flex items-center justify-center gap-3 py-3 px-4 rounded-lg transition-all",
              isActive 
                ? "bg-slate-900 dark:bg-[#d1d4dc] text-white dark:text-[#131722] shadow-md" 
                : "text-slate-500 dark:text-[#787b86] hover:bg-slate-50 dark:hover:bg-[#1e222d] hover:text-slate-900 dark:hover:text-[#d1d4dc]"
            )}
          >
            <span className={cn(
              "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border",
              isActive 
                ? "bg-white dark:bg-[#131722] text-slate-900 dark:text-[#d1d4dc] border-white dark:border-[#2a2e39]" 
                : "bg-slate-100 dark:bg-[#0d1117] text-slate-500 dark:text-[#787b86] border-slate-200 dark:border-[#2a2e39]"
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
