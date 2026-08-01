"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { Button } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import type { TopbarNavItem } from "./types";

type TopbarProps = {
  brandLabel: string;
  pageTitle: string;
  navItems: TopbarNavItem[];
  activeHref?: string;
  documentTitle?: string;
  onReady?: () => void;
  themeStorageKey?: string;
};

export function Topbar({
  brandLabel,
  pageTitle,
  navItems,
  activeHref,
  documentTitle,
  onReady,
  themeStorageKey = "finiq_theme",
}: TopbarProps) {
  const pathname = usePathname();
  const [isDark, setIsDark] = useState(false);
  const activeItem = activeHref
    ? navItems.find((item) => item.href === activeHref)
    : navItems.find((item) => item.href === pathname || item.paths?.includes(pathname));

  useEffect(() => {
    onReady?.();

    const isDarkMode = document.documentElement.classList.contains("dark") ||
      localStorage.getItem(themeStorageKey) === "dark" ||
      (!localStorage.getItem(themeStorageKey) && window.matchMedia("(prefers-color-scheme: dark)").matches);

    if (isDarkMode) {
      document.documentElement.classList.add("dark");
      setIsDark(true);
    }
  }, [onReady, themeStorageKey]);

  useEffect(() => {
    if (documentTitle) {
      document.title = documentTitle;
    }
  }, [documentTitle]);

  const toggleDarkMode = () => {
    if (isDark) {
      document.documentElement.classList.remove("dark");
      localStorage.setItem(themeStorageKey, "light");
      setIsDark(false);
    } else {
      document.documentElement.classList.add("dark");
      localStorage.setItem(themeStorageKey, "dark");
      setIsDark(true);
    }
  };

  return (
    <header className="mb-6 flex w-full max-w-full flex-col gap-2 overflow-hidden rounded-xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] p-2 shadow-[var(--tv-shadow)] transition-colors lg:min-h-16 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex w-full min-w-0 items-center justify-between gap-3 px-2 py-1 lg:w-auto lg:shrink-0">
        <div className="flex min-w-0 flex-col lg:flex-row lg:items-center lg:gap-3">
          <p className="truncate text-xs font-semibold uppercase tracking-wide text-[var(--tv-muted)]">{brandLabel}</p>
          <span aria-hidden="true" className="hidden h-7 w-px bg-[var(--tv-border)] lg:block" />
          <h1 className="truncate text-2xl font-bold text-[var(--tv-text)]">{pageTitle}</h1>
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={toggleDarkMode}
          className="border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] hover:text-[var(--tv-accent)] lg:hidden"
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        >
          {isDark ? <Sun className="h-4 w-4 text-[var(--tv-warning)]" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>

      <div className="flex w-full min-w-0 items-center gap-2 lg:w-auto lg:justify-end">
        <nav className="flex w-full min-w-0 gap-1 overflow-x-auto rounded-lg border border-[color:var(--tv-border)] bg-[var(--tv-surface-muted)] p-1 lg:w-auto" aria-label="주요 메뉴">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={activeItem?.href === item.href ? "page" : undefined}
              className={cn(
                "min-h-9 shrink-0 whitespace-nowrap rounded-md px-1.5 py-2 text-center text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-[var(--tv-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--tv-surface)] sm:px-4",
                activeItem?.href === item.href
                  ? "bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)]"
                  : "text-[var(--tv-muted)] hover:bg-[var(--tv-surface-raised)] hover:text-[var(--tv-text)]"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <Button
          variant="outline"
          size="icon"
          onClick={toggleDarkMode}
          className="hidden border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] transition-colors hover:text-[var(--tv-accent)] lg:flex"
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        >
          {isDark ? <Sun className="h-4 w-4 text-[var(--tv-warning)]" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
