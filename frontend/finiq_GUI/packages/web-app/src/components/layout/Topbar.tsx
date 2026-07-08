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
    <header className="mb-6 flex w-full max-w-full flex-col gap-4 overflow-hidden rounded-xl border border-[color:var(--tv-border)] bg-[var(--tv-surface)] px-4 py-3 shadow-[var(--tv-shadow)] backdrop-blur transition-colors md:flex-row md:items-center md:justify-between md:gap-5 md:px-5">
      <div className="flex w-full min-w-0 items-center justify-between gap-3 md:w-auto">
        <div className="min-w-0">
          <p className="text-sm font-medium uppercase text-[var(--tv-muted)]">{brandLabel}</p>
          <h1 className="mt-1 truncate text-2xl font-bold text-[var(--tv-text)]">
            {pageTitle}
          </h1>
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={toggleDarkMode}
          className="border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] hover:text-[var(--tv-accent)] md:hidden"
        >
          {isDark ? <Sun className="h-4 w-4 text-[var(--tv-warning)]" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>

      <div className="grid w-full min-w-0 gap-3 md:flex md:w-auto md:flex-nowrap md:items-center md:gap-4">
        <nav className="grid w-full min-w-0 grid-cols-1 gap-2 md:flex md:w-auto md:flex-nowrap" aria-label="주요 메뉴">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "min-w-0 overflow-hidden text-ellipsis whitespace-nowrap rounded-lg px-3 py-2 text-center text-sm font-medium transition-all md:px-4",
                activeItem?.href === item.href
                  ? "bg-[var(--tv-accent)] text-[var(--tv-accent-foreground)] shadow-sm"
                  : "text-[var(--tv-muted)] hover:text-[var(--tv-text)]"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="mx-1 hidden h-6 w-px bg-[var(--tv-border)] md:block" />

        <Button
          variant="outline"
          size="icon"
          onClick={toggleDarkMode}
          className="hidden border-[color:var(--tv-border)] bg-[var(--tv-surface)] text-[var(--tv-text)] transition-colors hover:text-[var(--tv-accent)] md:flex"
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        >
          {isDark ? <Sun className="h-4 w-4 text-[var(--tv-warning)]" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
    </header>
  );
}
