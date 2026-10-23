import "./globals.css";
import Notice from "./components/Notice";
import SiteFooter from "./components/SiteFooter";
import SiteHeader from "./components/SiteHeader";

export const metadata = {
  title: "Service Ops Intelligence",
  description: "Ask a question about field-service operations.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <SiteHeader />
        <div className="shell">
          <Notice />
          {children}
          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
