"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";
import ChannelRow from "./ChannelRow";
import MessagingChannelCard from "./MessagingChannelCard";

export type Channel = {
  id: string;
  type: "widget" | "whatsapp" | "instagram" | "email";
  mode: "auto" | "human";
  status: "pending" | "connected" | "disconnected" | "error";
  widget_key: string | null;
  display_name: string | null;
  color: string;
  position: "right" | "left";
  shape?: Shape;
};
type Shape = "circle" | "pill" | "rect";
const SHAPES: Shape[] = ["circle", "pill", "rect"];
// Dark text on a light colour, like the widget itself.
const textOn = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return (0.2126 * (n >> 16) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255 > 0.6 ? "#14161a" : "#fff";
};
const CHAT_ICON = "M12 2C6.48 2 2 6.04 2 11c0 2.7 1.34 5.11 3.46 6.74L4.5 22l4.78-2.04c.86.2 1.77.31 2.72.31 5.52 0 10-4.04 10-9S17.52 2 12 2z";

export type ChannelsData = { channels: Channel[]; max_channels: number; used: number; messaging_ready?: boolean };

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const fill = (s: string, v: Record<string, string | number>) => s.replace(/\{(\w+)\}/g, (_, k) => String(v[k] ?? ""));

export default function ChannelsManager({ initial, branding }: { initial: ChannelsData; branding: boolean }) {
  const { t } = useI18n();
  const c = t.channels;
  const [data, setData] = useState(initial);
  const widget = data.channels.find((x) => x.type === "widget") ?? null;
  const [form, setForm] = useState({
    color: widget?.color ?? "#0e9f6e",
    position: widget?.position ?? "right",
    shape: widget?.shape ?? ("circle" as Shape),
    mode: widget?.mode ?? "auto",
  });
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error" | "limit">("");
  const [copied, setCopied] = useState(false);
  // Which channel row is open (one at a time; all closed when the page opens).
  const [openRow, setOpenRow] = useState<string | null>(null);
  const toggle = (key: string, force?: boolean) =>
    setOpenRow((cur) => (force === true ? key : force === false ? null : cur === key ? null : key));

  const on = widget?.status === "connected";
  const roomLeft = data.used < data.max_channels;
  const router = useRouter();
  const params = useSearchParams();
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const handled = useRef(false);

  async function reload() {
    setData(await api<ChannelsData>("/channels"));
  }

  // Back from WhatsApp signup / Instagram login / mailbox sign-in: save the
  // account (the server checks with Zernio that it belongs to this business),
  // then clean the URL.
  useEffect(() => {
    const platform = params.get("connect");
    if (handled.current || (platform !== "whatsapp" && platform !== "instagram" && platform !== "email")) return;
    handled.current = true;
    const label = t.inbox.channelNames[platform];
    const accountId = params.get("accountId");
    const profileId = params.get("profileId");
    const error = params.get("error") || (params.get("status") === "error" ? "failed" : null);
    (async () => {
      if (accountId && (profileId || platform === "email") && !error) {
        try {
          await api(`/channels/${platform}/complete`, {
            method: "POST", body: JSON.stringify({ account_id: accountId, profile_id: profileId || undefined }),
          });
          await reload();
          setNotice({ ok: true, text: fill(c.connectedOk, { channel: label }) });
        } catch {
          setNotice({ ok: false, text: c.connectFailed });
        }
      } else if (error) {
        setNotice({ ok: false, text: error === "connection_cancelled" ? c.connectCancelled
          : error.includes("already_connected") || error.includes("pinned") ? c.numberTaken : c.connectFailed });
      }
      router.replace("/channels", { scroll: false });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  function messagingChannel(platform: "whatsapp" | "instagram" | "email") {
    return data.channels.find((x) => x.type === platform && x.status !== "disconnected") ?? null;
  }

  async function turnOn() {
    setBusy(true);
    setStatus("");
    try {
      const w = await api<Channel>("/channels/widget", { method: "POST" });
      setForm({ color: w.color, position: w.position, shape: w.shape ?? "circle", mode: w.mode });
      await reload();
      setOpenRow("widget");          // show the snippet right away
    } catch (e) {
      setStatus(e instanceof ApiError && e.status === 422 ? "limit" : "error");
    } finally {
      setBusy(false);
    }
  }

  async function update(values: Record<string, unknown>) {
    if (!widget) return;
    setBusy(true);
    setStatus("");
    try {
      await api(`/channels/${widget.id}`, { method: "PUT", body: JSON.stringify(values) });
      await reload();
      setStatus("saved");
    } catch (e) {
      setStatus(e instanceof ApiError && e.status === 422 && (e.detail as { code?: string })?.code === "channel_limit" ? "limit" : "error");
    } finally {
      setBusy(false);
    }
  }

  const snippet = widget?.widget_key
    ? `<script src="${API_URL}/widget/widget.js" data-key="${widget.widget_key}" async></script>`
    : "";

  async function copy() {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* the code is selectable anyway */ }
  }

  return (
    <>
      <p className="hint">{fill(c.usage, { used: data.used, max: data.max_channels })}</p>
      {notice && <div className={`alert ${notice.ok ? "alert-ok" : "alert-error"}`}>{notice.text}</div>}

      <div className="ch-list">
        <ChannelRow kind="widget" name={c.widgetTitle} className="channel-card channel-widget"
          open={openRow === "widget"} onToggle={() => toggle("widget")} settingsLabel={on}
          pill={widget ? <span className={`pill ${on ? "pill-on" : "pill-off"}`}>{on ? c.on : c.off}</span> : null}
          action={!on && roomLeft ? (
            <button className="btn btn-row" disabled={busy} onClick={turnOn}>{c.turnOn}</button>
          ) : null}>
          <p className="hint">{c.widgetDesc}</p>
          {!on && !roomLeft && <div className="alert alert-warn">{fill(c.limitReached, { n: data.max_channels })}</div>}
          {status === "limit" && <div className="alert alert-warn">{fill(c.limitReached, { n: data.max_channels })}</div>}
          {widget && !on && <p className="hint">{c.offNote}</p>}

          {widget && on && (
            <>
              <h3 className="sub-title">{c.snippetTitle}</h3>
              <p className="hint">{c.snippetHint}</p>
              <pre className="snippet" dir="ltr"><code>{snippet}</code></pre>
              <div className="actions actions-start">
                <button className="btn btn-auto" onClick={copy}>{copied ? c.copied : c.copy}</button>
                <a className="btn btn-secondary btn-auto" href={`${API_URL}/widget/${widget.widget_key}/demo`} target="_blank" rel="noopener">
                  {c.tryIt} ↗
                </a>
              </div>

              <div className="grid-2 channel-settings">
                <div className="field">
                  <label htmlFor="w-color">{c.color}</label>
                  <div className="color-row">
                    <input id="w-color" type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
                    <input dir="ltr" value={form.color} maxLength={7} onChange={(e) => setForm({ ...form, color: e.target.value })} />
                  </div>
                </div>
                <div className="field">
                  <label htmlFor="w-pos">{c.position}</label>
                  <select id="w-pos" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value as "right" | "left" })}>
                    <option value="right">{c.positions.right}</option>
                    <option value="left">{c.positions.left}</option>
                  </select>
                </div>
              </div>
              <div className="field">
                <label>{c.shape}</label>
                <div className="shape-tiles" role="radiogroup" aria-label={c.shape}>
                  {SHAPES.map((s) => (
                    <label key={s} className={`shape-tile${form.shape === s ? " on" : ""}`}>
                      <span className="shape-preview">
                        <span className={`shape-btn shape-${s}`}
                          style={(() => { const bg = /^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : "#0e9f6e"; return { background: bg, color: textOn(bg) }; })()}>
                          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={CHAT_ICON} /></svg>
                          {s !== "circle" && <span>{c.chatWithUs}</span>}
                        </span>
                      </span>
                      <span className="shape-name">
                        <input type="radio" name="w-shape" checked={form.shape === s} onChange={() => setForm({ ...form, shape: s })} />
                        {c.shapes[s]}
                      </span>
                    </label>
                  ))}
                </div>
                <span className="hint">{c.shapeHint}</span>
              </div>
              <div className="field">
                <label>{c.whoAnswers}</label>
                {(["auto", "human"] as const).map((m) => (
                  <label key={m} className="check">
                    <input type="radio" name="w-mode" checked={form.mode === m} onChange={() => setForm({ ...form, mode: m })} />
                    {c.modes[m]}
                  </label>
                ))}
              </div>
              {branding && <p className="hint">{c.branding}</p>}
              <div className="actions">
                {status === "saved" && <span className="saved">{c.saved}</span>}
                {status === "error" && <span className="error-text">{c.error}</span>}
                <button className="link-btn link-danger" disabled={busy} onClick={() => update({ enabled: false })}>{c.turnOff}</button>
                <button className="btn" disabled={busy || !/^#[0-9a-fA-F]{6}$/.test(form.color)}
                  onClick={() => update({ color: form.color, position: form.position, shape: form.shape, mode: form.mode })}>
                  {c.save}
                </button>
              </div>
            </>
          )}
        </ChannelRow>

        {(["whatsapp", "instagram", "email"] as const).map((p) => {
          const ch = messagingChannel(p);
          return (
            <MessagingChannelCard key={`${p}-${ch?.id ?? "none"}-${ch?.status ?? ""}`} platform={p} channel={ch}
              ready={data.messaging_ready !== false} roomLeft={roomLeft} maxChannels={data.max_channels} onChanged={reload}
              onConnected={() => setNotice({ ok: true, text: fill(c.connectedOk, { channel: t.inbox.channelNames[p] }) })}
              open={openRow === p} onToggle={(force) => toggle(p, force)} />
          );
        })}
      </div>
    </>
  );
}
