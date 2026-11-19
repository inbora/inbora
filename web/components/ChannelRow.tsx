"use client";

import { useI18n } from "@/lib/i18n/client";

/** One channel on the Channels page: a short row (name, status, account and
    its main action), which opens to show the channel's settings. */
export default function ChannelRow({ kind, name, pill, account, action, open, onToggle, className = "", settingsLabel = true, children }: {
  kind: "widget" | "whatsapp" | "instagram" | "email";
  name: string;
  pill?: React.ReactNode;
  account?: string | null;
  action?: React.ReactNode;
  open: boolean;
  onToggle?: () => void;
  className?: string;
  settingsLabel?: boolean;      // "Settings ▾" for set-up channels; just "▾" otherwise
  children?: React.ReactNode;
}) {
  const { t } = useI18n();
  const expandable = !!onToggle && !!children;
  return (
    <div className={`card ch-row ${className}${open ? " ch-open" : ""}`}>
      <div className={`ch-head${expandable ? " ch-click" : ""}`}
        role={expandable ? "button" : undefined} tabIndex={expandable ? 0 : undefined} aria-expanded={expandable ? open : undefined}
        onClick={expandable ? onToggle : undefined}
        onKeyDown={expandable ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggle!(); } } : undefined}>
        <span className={`chan-dot chan-dot-${kind}`} aria-hidden="true" />
        <span className="ch-name">{name}</span>
        {pill}
        {account && <span className="ch-acct" dir="ltr">{account}</span>}
        <span className="ch-space" />
        {action && <span className="ch-action" onClick={(e) => e.stopPropagation()}>{action}</span>}
        {expandable && (
          <span className="ch-chev">{settingsLabel ? `${t.channels.settings} ` : ""}{open ? "▴" : "▾"}</span>
        )}
      </div>
      {expandable && open && <div className="ch-body">{children}</div>}
    </div>
  );
}
