"use client";

import type { ReactNode } from "react";

type AppFrameProps = {
  children: ReactNode;
  topbar?: ReactNode;
};

export function AppFrame({ children, topbar }: AppFrameProps) {
  return (
    <div className="mx-auto box-border flex min-h-dvh w-full min-w-0 max-w-[92rem] flex-col overflow-x-clip px-8 py-5 sm:px-10 lg:px-14 lg:py-7 xl:px-16">
      {topbar}
      {children}
    </div>
  );
}
