"use client";

import { usePathname } from "next/navigation";
import { cn } from "@finiq/ui/utils";
import { Topbar } from "./Topbar";

type AppFrameProps = {
  children: React.ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  const pathname = usePathname();
  const isOntology = pathname === "/" || pathname?.startsWith("/graph");

  return (
    <div
      className={cn(
        "mx-auto box-border flex min-h-screen w-full min-w-0 max-w-full flex-col overflow-x-hidden p-4 md:px-7 md:py-8",
        isOntology ? "w-full max-w-[96rem]" : "max-w-7xl",
      )}
    >
      <Topbar />
      {children}
    </div>
  );
}
