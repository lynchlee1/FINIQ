"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";
import type { WorkflowTab } from "./types";

type WorkflowTabsProps = {
  tabs: WorkflowTab[];
};

export function WorkflowTabs({ tabs }: WorkflowTabsProps) {
  const pathname = usePathname();

  return (
    <nav className="overflow-x-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-1 transition-colors" aria-label="Workflow steps">
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
                  ? "bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                  : "text-[var(--tv-muted)] hover:text-[var(--tv-text)]"
              )}
            >
              <span className={cn(
                "flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-semibold",
                isActive
                  ? "border-[color:var(--tv-accent-foreground)] bg-[var(--tv-accent-foreground)] text-[var(--tv-accent)]"
                  : "border-[color:var(--tv-border)] bg-[var(--tv-control)] text-[var(--tv-muted)]"
              )}>
                {tab.step}
              </span>
              <span className="text-sm font-medium">{tab.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
