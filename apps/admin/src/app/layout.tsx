import type { Metadata } from "next";
import type { ReactNode } from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import { ToastContainer } from "../components/toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wulkan Admin",
  description: "Backoffice operativo de Wulkan"
};

export default function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="es">
      <body>
        {children}
        <ToastContainer />
      </body>
    </html>
  );
}
