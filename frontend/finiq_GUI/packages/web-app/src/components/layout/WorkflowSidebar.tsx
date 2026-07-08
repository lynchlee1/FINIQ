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
    <aside className="w-full min-w-0 self-start rounded-2xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-3 shadow-[var(--tv-shadow)] backdrop-blur transition-colors lg:sticky lg:top-7">
      <nav className="space-y-3" aria-label={title}>
        {resolvedGroups.map((group) => (
          <section key={group.label} className="overflow-hidden rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface)]">
            <h3 className="text-body flex min-h-10 items-center gap-2 border-b border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-3 font-bold text-[var(--tv-text)]">
              <span className="h-4 w-1 rounded-full bg-[var(--tv-accent)]" aria-hidden="true" />
              <span className="min-w-0 truncate">{group.label}</span>
            </h3>
            <div className="space-y-1 p-1.5">
              {group.steps.map((tab) => {
                const isActive = pathname === tab.href;
                return (
                  <Link
                    key={tab.href}
                    href={tab.href}
                    className={cn(
                      "text-body flex min-h-10 items-center rounded-lg px-3 py-2.5 font-medium transition-all",
                      isActive
                        ? "bg-[var(--tv-accent)] text-white shadow-sm"
                        : "text-[var(--tv-muted)] hover:text-[var(--tv-text)]"
                    )}
                  >
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
