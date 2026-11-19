"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import LanguageSwitcher from "./LanguageSwitcher";
import Logo from "./Logo";
import { api } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

const ICONS: Record<string, string> = {
  inbox: "M3 13h5l2 3h4l2-3h5M5 5h14l2 8v6H3v-6z",
  channels: "M8 12a4 4 0 1 0 8 0 4 4 0 0 0-8 0M12 2v4M12 18v4M2 12h4M18 12h4",
  knowledge: "M4 5a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2zM4 21V5M8 7h6M8 11h6",
  agent: "M12 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M4 21a8 8 0 0 1 16 0",
  plan: "M3 6h18v12H3zM3 10h18M7 15h3",
  settings: "M12 9a3 3 0 1 1 0 6 3 3 0 0 1 0-6M19 12l2-1-1-3-2 .2-1.5-1.5L17 4l-3-1-1 2h-2L10 3 7 4l.5 2.7L6 8.2 4 8l-1 3 2 1v1l-2 1 1 3 2-.2 1.5 1.5L7 20l3 1 1-2h2l1 2 3-1-.5-2.7 1.5-1.5 2 .2 1-3-2-1z",
  admin: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
};

function Icon({ name }: { name: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

const ITEMS = ["inbox", "channels", "knowledge", "agent", "plan", "settings"] as const;

export default function Sidebar({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n();
  const path = usePathname();
  const [waiting, setWaiting] = useState(0);

  // Conversations waiting for the team, refreshed every 30 seconds.
  useEffect(() => {
    let stop = false;
    const load = () => {
      if (document.hidden) return;
      api<{ escalated: number }>("/inbox/counts").then((c) => !stop && setWaiting(c.escalated)).catch(() => {});
    };
    load();
    const id = setInterval(load, 30000);
    return () => { stop = true; clearInterval(id); };
  }, [path]);

  const link = (key: keyof typeof t.nav) => {
    const href = `/${key}`;
    const active = path === href || path.startsWith(href + "/");
    return (
      <Link key={key} href={href} className={`side-link${active ? " active" : ""}`}>
        <Icon name={key} />
        {t.nav[key]}
        {key === "inbox" && waiting > 0 && <span className="side-count">{waiting > 99 ? "99+" : waiting}</span>}
      </Link>
    );
  };

  return (
    <aside className="side">
      <div className="side-brand">
        <Logo /> {t.appName}
      </div>
      <nav className="side-nav">
        {ITEMS.map(link)}
        {isAdmin && (
          <>
            <div className="side-sep" />
            {link("admin")}
          </>
        )}
      </nav>
      <div className="side-foot">
        <LanguageSwitcher />
        <form action="/auth/signout" method="post">
          <button className="btn btn-ghost">{t.nav.logout}</button>
        </form>
      </div>
    </aside>
  );
}
