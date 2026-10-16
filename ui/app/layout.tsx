import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Shell from "@/components/Shell";
import { StoreProvider } from "@/lib/store";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-geist", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-geist-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Nodus",
  description: "Who owns what, who knows what, and why. Every answer cited, every change dated.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${mono.variable}`}>
      <body>
        <StoreProvider>
          <Shell>{children}</Shell>
        </StoreProvider>
      </body>
    </html>
  );
}
