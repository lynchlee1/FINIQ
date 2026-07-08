"use client"

import { useCallback } from "react";
import { usePathname } from "next/navigation";
import { Topbar as WebAppTopbar } from "@finiq/web-app/layout";
import { getActiveNavItem, getPageTitle, NAV_ITEMS } from "@/config/navigation";
import { useSettingsStore } from "@/store/useSettingsStore";

export function Topbar() {
  const pathname = usePathname();
  const { fetchRuntimeInfo } = useSettingsStore();
  const activeItem = getActiveNavItem(pathname);
  const pageTitle = getPageTitle(pathname) || activeItem?.label || "Ontology";
  const handleReady = useCallback(() => {
    fetchRuntimeInfo();
  }, [fetchRuntimeInfo]);

  return (
    <WebAppTopbar
      brandLabel="FINIQ MarketDesk"
      pageTitle={pageTitle}
      navItems={NAV_ITEMS}
      activeHref={activeItem?.href}
      documentTitle={`${pageTitle} | FINIQ MarketDesk`}
      onReady={handleReady}
    />
  );
}
