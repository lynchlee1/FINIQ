"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";
import type { SidebarGroup, WorkflowTab } from "./types";

type WorkflowSidebarProps = {
  title: string;
  tabs?: WorkflowTab[];
  groups?: SidebarGroup[];
};

export function WorkflowSidebar({ title, tabs = [], groups }: WorkflowSidebarProps) {
  const pathname = usePathname();
  const resolvedGroups = groups ?? [{ label: "Workflow", steps: tabs }];

  return (
    <aside className="w-full min-w-0 self-start rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-4 transition-colors lg:sticky lg:top-7">
      <nav className="space-y-5" aria-label={title}>
        {resolvedGroups.map((group) => (
          <section key={group.label} className="space-y-1">
            <h3 className="px-3 pb-1 text-base font-bold text-[var(--tv-text)]">
              <span className="min-w-0 truncate">{group.label}</span>
            </h3>
            <div className="space-y-1">
              {group.steps.map((tab) => {
                const isActive = pathname === tab.href;
                return (
                  <Link
                    key={tab.href}
                    href={tab.href}
                    className={cn(
                      "flex items-center rounded-lg py-2.5 pr-3 text-sm font-medium transition-all",
                      group.numbered ? "gap-1 pl-3" : "pl-6",
                      isActive
                        ? "bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                        : "text-[var(--tv-muted)] hover:text-[var(--tv-text)]"
                    )}
                  >
                    {group.numbered ? (
                      <span className="w-5 shrink-0 text-xs font-semibold tabular-nums opacity-80">
                        {String(tab.step).padStart(2, "0")}
                      </span>
                    ) : null}
                    <span className="min-w-0 truncate">{tab.label}</span>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  );
}
