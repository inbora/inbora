import Link from "next/link";
import Logo from "@/components/Logo";

/** Public pages anyone can open: Terms, Privacy, data deletion. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="public-wrap" dir="ltr" lang="en">
      <header className="public-head">
        <Link href="/" className="auth-brand public-brand"><Logo /> Inbora</Link>
      </header>
      <main className="public-main">{children}</main>
      <footer className="public-foot">
        <Link href="/terms">Terms of Service</Link>
        <Link href="/privacy">Privacy Policy</Link>
        <Link href="/data-deletion">Data deletion</Link>
        <a href="mailto:contact@inbora.ai">contact@inbora.ai</a>
      </footer>
    </div>
  );
}
