import type { Metadata } from "next";
import { Open_Sans } from "next/font/google";
import { Shell } from "@/components/shell/Shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const openSans = Open_Sans({ variable: "--font-open-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Jessi · JFrog competitive intelligence",
  description: "Jessi, JFrog's Engine for Strategic Signals & Intelligence: daily competitive intelligence for the JFrog CI team",
  icons: {
    icon: [
      { url: "/brand/jessi-icon.svg", type: "image/svg+xml" },
      { url: "/brand/jessi-icon-32.png", sizes: "32x32", type: "image/png" },
    ],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${openSans.variable} font-sans antialiased`}>
        <TooltipProvider>
          <Shell>{children}</Shell>
        </TooltipProvider>
      </body>
    </html>
  );
}
