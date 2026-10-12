import "./globals.css";

export const metadata = {
  title: "Service Ops Intelligence",
  description: "Ask a question about field-service operations.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
