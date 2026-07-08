"use client";

import { Topbar } from "./Topbar";

type AppFrameProps = {
  children: React.ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  return (
    <div className="mx-auto box-border flex min-h-dvh w-full min-w-0 max-w-[92rem] flex-col overflow-x-hidden px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
      <Topbar />
      {children}
    </div>
  );
}
