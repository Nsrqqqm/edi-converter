import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PDF → EDI Converter",
  description:
    "Extract vendor PDF invoices into fixed-width EDI files using Google Gemini.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased dark:bg-gray-950 dark:text-gray-100">
        {children}
      </body>
    </html>
  );
}
