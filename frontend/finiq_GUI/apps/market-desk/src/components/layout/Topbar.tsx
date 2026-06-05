"use client"

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sun, Moon } from "lucide-react";
import { Button } from "@finiq/ui";
import { cn } from "@finiq/ui/utils";
import { getActiveNavItem, NAV_ITEMS } from "@/config/navigation";

export function Topbar() {
  const pathname = usePathname();
  const [isDark, setIsDark] = useState(false);
  const activeItem = getActiveNavItem(pathname);

  useEffect(() => {
    // Initial check
    const isDarkMode = document.documentElement.classList.contains("dark") || 
                       localStorage.getItem("finiq_theme") === "dark" ||
                       (!localStorage.getItem("finiq_theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    
    if (isDarkMode) {
      document.documentElement.classList.add("dark");
      setIsDark(true);
    }
  }, []);

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
    <header className="bg-white dark:bg-[#161b22] rounded-xl shadow-sm border border-slate-200 dark:border-[#30363d] p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6 transition-colors">
      <div className="flex items-center justify-between w-full md:w-auto">
        <div>
          <p className="text-sm font-medium text-slate-500 dark:text-slate-500 uppercase tracking-wider">FINIQ MarketDesk</p>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            {activeItem?.label || "Ontology"}
          </h1>
        </div>
        <Button 
          variant="outline" 
          size="icon" 
          onClick={toggleDarkMode} 
          className="md:hidden border-slate-200 dark:border-[#30363d] dark:hover:bg-[#21262d]"
        >
          {isDark ? <Sun className="h-4 w-4 text-amber-400" /> : <Moon className="h-4 w-4 text-slate-600" />}
        </Button>
      </div>
      
      <div className="flex items-center gap-4">
        <nav className="flex gap-2 flex-wrap" aria-label="주요 메뉴">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
                activeItem?.href === item.href
                  ? "bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900"
                  : "text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-[#21262d] dark:hover:text-slate-100"
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        
        <div className="hidden md:block h-6 w-px bg-slate-200 dark:bg-[#30363d] mx-1" />
        
        <Button 
          variant="outline" 
          size="icon" 
          onClick={toggleDarkMode} 
          className="hidden md:flex border-slate-200 dark:border-[#30363d] dark:hover:bg-[#21262d] transition-colors"
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
        >
          {isDark ? <Sun className="h-[1.1rem] w-[1.1rem] text-amber-400" /> : <Moon className="h-[1.1rem] w-[1.1rem] text-slate-600" />}
        </Button>
      </div>
    </header>
  );
}
