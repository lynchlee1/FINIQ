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
    <aside className="w-full min-w-0 self-start rounded-xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-4 shadow-[var(--tv-shadow)] backdrop-blur transition-colors lg:sticky lg:top-7">
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
                      "flex items-center rounded-lg py-2.5 pl-6 pr-3 text-sm font-medium transition-all",
                      isActive
                        ? "bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)] shadow-sm"
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
