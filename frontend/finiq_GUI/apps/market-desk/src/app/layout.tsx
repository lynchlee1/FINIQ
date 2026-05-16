import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Topbar } from "@/components/layout/Topbar";
import { cn } from "@finiq/ui/utils";

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
      <body className={cn(inter.className, "antialiased")}>
        <div className="max-w-6xl mx-auto p-4 md:p-8 flex flex-col min-h-screen">
          <Topbar />
          {children}
        </div>
      </body>
    </html>
  );
}
