import type { Metadata } from "next";
import { Open_Sans } from "next/font/google";
import { Shell } from "@/components/shell/Shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

const openSans = Open_Sans({ variable: "--font-open-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Jessie · JFrog competitive intelligence",
  description: "Daily competitive intelligence for the JFrog CI team",
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
