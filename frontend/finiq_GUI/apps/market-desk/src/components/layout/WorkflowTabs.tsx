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
    <nav className="bg-white rounded-xl shadow-sm border border-slate-200 p-1 flex gap-1 mb-6" aria-label="Workflow steps">
      {tabs.map((tab) => {
        const isActive = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={cn(
              "flex-1 flex items-center justify-center gap-3 py-3 px-4 rounded-lg transition-all",
              isActive 
                ? "bg-slate-900 text-white shadow-md" 
                : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
            )}
          >
            <span className={cn(
              "w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold border",
              isActive 
                ? "bg-white text-slate-900 border-white" 
                : "bg-slate-100 text-slate-500 border-slate-200"
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
