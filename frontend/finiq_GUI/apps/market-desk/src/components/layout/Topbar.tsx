"use client"

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";

const NAV_ITEMS = [
  { href: "/", label: "공시 조회" },
  { href: "/download", label: "공시데이터 구축" },
  { href: "/html-download", label: "원문 처리" },
  { href: "/integrated-data", label: "종합데이터 구축" },
];

export function Topbar() {
  const pathname = usePathname();

  return (
    <header className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
      <div>
        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">FINIQ MarketDesk</p>
        <h1 className="text-2xl font-bold text-slate-900">
          {NAV_ITEMS.find((item) => item.href === pathname)?.label || "공시 조회"}
        </h1>
      </div>
      <nav className="flex gap-2 flex-wrap" aria-label="주요 메뉴">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium transition-colors",
              pathname === item.href
                ? "bg-slate-900 text-white"
                : "text-slate-600 hover:bg-slate-100"
            )}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
