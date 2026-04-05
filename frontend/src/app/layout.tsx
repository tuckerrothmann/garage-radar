import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "Garage Radar",
  description: "Collector vehicle market intelligence",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <Nav />
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8">
          {children}
        </main>
      </body>
    </html>
  );
}
