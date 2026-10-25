import type { Metadata } from "next";
import { Fraunces, Plus_Jakarta_Sans } from "next/font/google";

import { AppShell } from "@/components/layout/app-shell";
import { ToastProvider } from "@/components/ui/toast";

import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
});

export const metadata: Metadata = {
  title: "THE CRITICAL 1% — Let's Keep Our Communities Safe!",
  description:
    "Find places that may need help, learn why, and see what we can do — multi-city community vulnerability app.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${jakarta.variable} ${fraunces.variable} font-sans antialiased`}
      >
        <ToastProvider>
          <AppShell>{children}</AppShell>
        </ToastProvider>
      </body>
    </html>
  );
}
