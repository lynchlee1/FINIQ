"use client";

import { AppFrame as WebAppFrame } from "@finiq/web-app";
import { Topbar } from "./Topbar";

type AppFrameProps = {
  children: React.ReactNode;
};

export function AppFrame({ children }: AppFrameProps) {
  return (
    <WebAppFrame topbar={<Topbar />}>
      {children}
    </WebAppFrame>
  );
}
