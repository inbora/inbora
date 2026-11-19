"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";
import ChannelRow from "./ChannelRow";
import type { Channel } from "./ChannelsManager";

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** WhatsApp, Instagram or email: one-click connect (through Zernio), status,
    who answers, reconnect and disconnect — as a row that opens. */
export default function MessagingChannelCard({ platform, channel, ready, roomLeft, maxChannels, onChanged, open, onToggle }: {
  platform: "whatsapp" | "instagram" | "email";
  channel: Channel | null;
  ready: boolean;
  roomLeft: boolean;
  maxChannels: number;
  onChanged: () => Promise<void>;
  open: boolean;
  onToggle: (open?: boolean) => void;
}) {
  const { t } = useI18n();
  const c = t.channels;
  const name = t.inbox.channelNames[platform];
  const [useApp, setUseApp] = useState(true);
  const [mode, setMode] = useState<"auto" | "human">(channel?.mode ?? (platform === "email" ? "human" : "auto"));
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error" | "limit">("");

  const state = !channel ? "none" : channel.status === "error" ? "error" : "connected";

  async function connect() {
    setBusy(true);
    setStatus("");
    try {
      const r = await api<{ url: string }>(`/channels/${platform}/connect`, {
        method: "POST", body: JSON.stringify({ whatsapp_app: useApp }),
      });
      window.location.href = r.url;       // Meta's own signup / Instagram login / mailbox sign-in
    } catch (e) {
      setStatus(e instanceof ApiError && e.status === 422 ? "limit" : "error");
      onToggle(true);
      setBusy(false);
    }
  }

  async function saveMode() {
    if (!channel) return;
    setBusy(true);
    setStatus("");
    try {
      await api(`/channels/${channel.id}`, { method: "PUT", body: JSON.stringify({ mode }) });
      await onChanged();
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    if (!channel || !window.confirm(fill(c.confirmDisconnect, { channel: name }))) return;
    setBusy(true);
    setStatus("");
    try {
      await api(`/channels/${channel.id}/disconnect`, { method: "POST" });
      await onChanged();
    } catch {
      setStatus("error");
    } finally {
      setBusy(false);
    }
  }

  // The one action shown on the closed row.
  let action: React.ReactNode = null;
  const connectLabel = busy ? c.connecting : fill(c.connect, { channel: name });
  if (state === "none") {
    // WhatsApp first shows its "Business app / other number" choice;
    // Instagram and email connect straight away. No room or not ready: open to explain.
    const direct = platform !== "whatsapp" && ready && roomLeft;
    action = open && !direct ? null : (
      <button className="btn btn-row" disabled={busy} onClick={() => (direct ? connect() : onToggle(true))}>
        {connectLabel}
      </button>
    );
  } else if (state === "error") {
    action = (
      <button className="btn btn-row" disabled={busy || !ready} onClick={connect}>
        {busy ? c.connecting : c.reconnect}
      </button>
    );
  }

  return (
    <ChannelRow kind={platform} name={name} className={`channel-${platform}`} open={open} onToggle={() => onToggle()}
      settingsLabel={state === "connected"}
      account={channel?.display_name}
      pill={state === "connected" ? <span className="pill pill-on">{c.on}</span>
        : state === "error" ? <span className="pill pill-error">{c.errorPill}</span> : null}
      action={action}>
      <p className="hint">{platform === "whatsapp" ? c.whatsappDesc : platform === "email" ? c.emailDesc : c.instagramDesc}</p>

      {!ready && state === "none" && <p className="hint">{c.notReady}</p>}

      {ready && state === "none" && (
        <>
          {platform === "whatsapp" && (
            <div className="field">
              {[true, false].map((app) => (
                <label key={String(app)} className="check">
                  <input type="radio" name="wa-onboarding" checked={useApp === app} onChange={() => setUseApp(app)} />
                  {app ? c.waAppOption : c.waApiOption}
                </label>
              ))}
            </div>
          )}
          {platform === "instagram" && <p className="hint">{c.igNote}</p>}
          {!roomLeft ? (
            <div className="alert alert-warn">{fill(c.limitReached, { n: maxChannels })}</div>
          ) : (
            <div className="actions actions-start">
              <button className="btn btn-auto ch-connect" disabled={busy} onClick={connect}>{connectLabel}</button>
            </div>
          )}
        </>
      )}

      {state === "error" && (
        <>
          <div className="alert alert-error">{c.errorNote}</div>
          <div className="actions actions-start">
            <button className="link-btn link-danger" disabled={busy} onClick={disconnect}>{c.disconnect}</button>
          </div>
        </>
      )}

      {state === "connected" && (
        <>
          <div className="field">
            <label>{c.whoAnswers}</label>
            {(["auto", "human"] as const).map((m) => (
              <label key={m} className="check">
                <input type="radio" name={`${platform}-mode`} checked={mode === m} onChange={() => { setMode(m); setStatus(""); }} />
                {c.modes[m]}
              </label>
            ))}
          </div>
          <div className="actions">
            {status === "saved" && <span className="saved">{c.saved}</span>}
            <button className="link-btn link-danger" disabled={busy} onClick={disconnect}>{c.disconnect}</button>
            <button className="btn" disabled={busy || mode === channel?.mode} onClick={saveMode}>{c.save}</button>
          </div>
        </>
      )}

      {status === "limit" && <div className="alert alert-warn">{fill(c.limitReached, { n: maxChannels })}</div>}
      {status === "error" && <p className="error-text">{c.error}</p>}
    </ChannelRow>
  );
}
