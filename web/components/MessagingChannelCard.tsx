"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";
import type { Channel } from "./ChannelsManager";

const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

/** WhatsApp or Instagram: one-click connect (through Zernio), status,
    who answers, reconnect and disconnect. */
export default function MessagingChannelCard({ platform, channel, ready, roomLeft, maxChannels, onChanged }: {
  platform: "whatsapp" | "instagram";
  channel: Channel | null;
  ready: boolean;
  roomLeft: boolean;
  maxChannels: number;
  onChanged: () => Promise<void>;
}) {
  const { t } = useI18n();
  const c = t.channels;
  const name = t.inbox.channelNames[platform];
  const [useApp, setUseApp] = useState(true);
  const [mode, setMode] = useState<"auto" | "human">(channel?.mode ?? "auto");
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
      window.location.href = r.url;       // Meta's own signup / Instagram login
    } catch (e) {
      setStatus(e instanceof ApiError && e.status === 422 ? "limit" : "error");
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

  return (
    <div className={`card channel-card channel-${platform}`}>
      <div className="row-between">
        <div className="grow">
          <h2 className="channel-title">
            <span className={`chan-dot chan-dot-${platform}`} aria-hidden="true" />
            {name}
            {state === "connected" && <span className="pill pill-on">{c.on}</span>}
            {state === "error" && <span className="pill pill-error">{c.errorPill}</span>}
          </h2>
          {channel?.display_name && <div className="account-name" dir="ltr">{channel.display_name}</div>}
          <p className="hint">{platform === "whatsapp" ? c.whatsappDesc : c.instagramDesc}</p>
        </div>
      </div>

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
              <button className="btn btn-auto" disabled={busy} onClick={connect}>
                {busy ? c.connecting : fill(c.connect, { channel: name })}
              </button>
            </div>
          )}
        </>
      )}

      {state === "error" && (
        <>
          <div className="alert alert-error">{c.errorNote}</div>
          <div className="actions actions-start">
            <button className="btn btn-auto" disabled={busy || !ready} onClick={connect}>
              {busy ? c.connecting : c.reconnect}
            </button>
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
    </div>
  );
}
