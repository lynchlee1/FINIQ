"use client";

import type { ReactNode } from "react";

type AppFrameProps = {
  children: ReactNode;
  topbar?: ReactNode;
};

export function AppFrame({ children, topbar }: AppFrameProps) {
  return (
    <div className="mx-auto box-border flex min-h-dvh w-full min-w-0 max-w-[92rem] flex-col overflow-x-hidden px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
      {topbar}
      {children}
    </div>
  );
}
