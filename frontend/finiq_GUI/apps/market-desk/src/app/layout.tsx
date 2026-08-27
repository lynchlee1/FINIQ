import type { Metadata } from "next";
import "@fontsource/ibm-plex-sans-kr/korean-400.css";
import "@fontsource/ibm-plex-sans-kr/korean-500.css";
import "@fontsource/ibm-plex-sans-kr/korean-600.css";
import "@fontsource/ibm-plex-sans-kr/korean-700.css";
import "@fontsource-variable/space-grotesk";
import "./globals.css";
import { AppFrame } from "@/components/layout/AppFrame";

export const metadata: Metadata = {
  title: "FINIQ MarketDesk",
  description: "FINIQ MarketDesk 공시 조회",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="antialiased">
        <AppFrame>
          {children}
        </AppFrame>
      </body>
    </html>
  );
}
