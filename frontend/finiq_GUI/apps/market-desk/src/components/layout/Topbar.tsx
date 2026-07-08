"use client"

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Moon, Sun } from "lucide-react";
import { Button } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { getActiveNavItem, getPageTitle, NAV_ITEMS } from "@/config/navigation";
import { useSettingsStore } from "@/store/useSettingsStore";

export function Topbar() {
  const pathname = usePathname();
  const { fetchRuntimeInfo } = useSettingsStore();
  const [isDark, setIsDark] = useState(false);
  const activeItem = getActiveNavItem(pathname);
  const pageTitle = getPageTitle(pathname) || activeItem?.label || "Ontology";

  useEffect(() => {
    fetchRuntimeInfo();

    // Initial check
    const isDarkMode = document.documentElement.classList.contains("dark") || 
                       localStorage.getItem("finiq_theme") === "dark" ||
                       (!localStorage.getItem("finiq_theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    
    if (isDarkMode) {
      document.documentElement.classList.add("dark");
      setIsDark(true);
    }
  }, [fetchRuntimeInfo]);

  useEffect(() => {
    document.title = `${pageTitle} | FINIQ MarketDesk`;
  }, [pageTitle]);

  const toggleDarkMode = () => {
    if (isDark) {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("finiq_theme", "light");
      setIsDark(false);
    } else {
      document.documentElement.classList.add("dark");
      localStorage.setItem("finiq_theme", "dark");
      setIsDark(true);
    }
  };

  return (
    <header className="mb-6 flex w-full max-w-full flex-col gap-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-[0_18px_45px_-32px_rgba(15,23,42,0.55)] backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-900/90 md:flex-row md:items-center md:justify-between md:gap-5 md:px-5">
      <div className="flex w-full min-w-0 items-center justify-between gap-3 md:w-auto">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold tracking-[0.18em] text-slate-500 dark:text-slate-400">FINIQ MarketDesk</p>
          <h1 className="mt-1 truncate text-xl font-semibold leading-tight text-slate-950 dark:text-slate-50">
            {pageTitle}
          </h1>
        </div>
        <Button 
          variant="outline" 
          size="icon" 
          onClick={toggleDarkMode} 
          className="md:hidden border-slate-200 bg-white/70 text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4" />}
        </Button>
      </div>
      
      <div className="grid w-full min-w-0 gap-3 md:flex md:w-auto md:flex-nowrap md:items-center md:gap-3">
        <nav className="grid w-full min-w-0 grid-cols-2 gap-1 rounded-xl bg-slate-100/80 p-1 dark:bg-slate-950/55 sm:grid-cols-4 md:flex md:w-auto md:flex-nowrap" aria-label="주요 메뉴">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "min-w-0 overflow-hidden text-ellipsis whitespace-nowrap rounded-lg px-3 py-2 text-center text-sm font-medium transition-all md:px-4",
                activeItem?.href === item.href
                  ? "bg-white text-slate-950 shadow-sm ring-1 ring-slate-200/80 dark:bg-slate-800 dark:text-slate-50 dark:ring-slate-700"
                  : "text-slate-600 hover:bg-white/70 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-800/70 dark:hover:text-slate-100"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        
        <div className="mx-1 hidden h-6 w-px bg-slate-200 dark:bg-slate-700 md:block" />
        
        <Button 
          variant="outline" 
          size="icon" 
          onClick={toggleDarkMode} 
          className="hidden border-slate-200 bg-white/70 text-slate-700 transition-colors dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200 dark:hover:bg-slate-800 md:flex"
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        >
          {isDark ? <Sun className="h-[1.1rem] w-[1.1rem] text-amber-400" /> : <Moon className="h-[1.1rem] w-[1.1rem]" />}
        </Button>
      </div>
    </header>
  );
}
