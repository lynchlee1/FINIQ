import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Topbar } from "@/components/layout/Topbar";

const inter = Inter({ subsets: ["latin"] });

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
      <body className={inter.className}>
        <div className="min-h-screen bg-slate-50 p-4 md:p-8 max-w-6xl mx-auto flex flex-col">
          <Topbar />
          {children}
        </div>
      </body>
    </html>
  );
}
