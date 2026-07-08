import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppFrame } from "@/components/layout/AppFrame";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

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
    <html lang="ko" className={inter.variable}>
      <body className="antialiased">
        <AppFrame>
          {children}
        </AppFrame>
      </body>
    </html>
  );
}
