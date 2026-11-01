import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AgentPass — управление полномочиями ИИ-агентов",
  description:
    "Финансовые полномочия под вашим контролем. Инфраструктурный sandbox AgentPass.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
