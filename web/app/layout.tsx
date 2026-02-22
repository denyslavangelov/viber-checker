import type { Metadata } from "next";
import { Geologica } from "next/font/google";
import "./globals.css";

const geologica = Geologica({
  subsets: ["latin", "cyrillic"],
  variable: "--font-geologica",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Viber екранна снимка",
  description: "Въведете телефонен номер, за да заснемете екран от чат в Viber",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="bg" className={geologica.variable}>
      <body className="antialiased min-h-screen bg-[#0a0a0c] text-white font-sans safe-area-padding">
        {children}
      </body>
    </html>
  );
}
