import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pianova — Piano transcription workspace",
  description: "Turn solo-piano performances into readable, editable music.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
