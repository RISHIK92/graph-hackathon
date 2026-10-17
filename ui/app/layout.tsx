import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Shell from "@/components/Shell";
import { StoreProvider } from "@/lib/store";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-geist", display: "swap" });
const mono = Geist_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-geist-mono", display: "swap" });

const THEME_SCRIPT = `try{var t=localStorage.getItem("nodus.theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: light)").matches?"light":"dark";document.documentElement.dataset.theme=t}catch(e){}`;

export const metadata: Metadata = {
  title: "Nodus",
  description: "Who owns what, who knows what, and why. Every answer cited, every change dated.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} ${mono.variable}`} data-theme="dark" suppressHydrationWarning>
      <head>
        {/* the theme before first paint (no flash): the saved choice, else the OS preference on a first visit */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <StoreProvider>
          <Shell>{children}</Shell>
        </StoreProvider>
      </body>
    </html>
  );
}
