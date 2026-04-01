import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ContextCore — Institutional Memory Intelligence",
  description: "Enterprise knowledge graph powered by GraphRAG",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
