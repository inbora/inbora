import type { Metadata } from "next";
import { I18nProvider } from "@/lib/i18n/client";
import { getI18n } from "@/lib/i18n/server";
import "./globals.css";

export const metadata: Metadata = {
  title: "Inbora",
  description: "AI customer service for WhatsApp, Instagram, email and your website",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { lang, dir } = await getI18n();
  return (
    <html lang={lang} dir={dir}>
      <body>
        <I18nProvider lang={lang}>{children}</I18nProvider>
      </body>
    </html>
  );
}
