"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

export type Channel = {
  id: string;
  type: "widget" | "whatsapp" | "instagram" | "email";
  mode: "auto" | "human";
  status: "pending" | "connected" | "disconnected" | "error";
  widget_key: string | null;
  color: string;
  position: "right" | "left";
};

export type ChannelsData = { channels: Channel[]; max_channels: number; used: number };

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
    mode: widget?.mode ?? "auto",
  });
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error" | "limit">("");
  const [copied, setCopied] = useState(false);

  const on = widget?.status === "connected";
  const roomLeft = data.used < data.max_channels;

  async function reload() {
    setData(await api<ChannelsData>("/channels"));
  }

  async function turnOn() {
    setBusy(true);
    setStatus("");
    try {
      const w = await api<Channel>("/channels/widget", { method: "POST" });
      setForm({ color: w.color, position: w.position, mode: w.mode });
      await reload();
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

      <div className="card channel-card">
        <div className="row-between">
          <div className="grow">
            <h2 className="channel-title">
              {c.widgetTitle}
              {widget && <span className={`pill ${on ? "pill-on" : "pill-off"}`}>{on ? c.on : c.off}</span>}
            </h2>
            <p className="hint">{c.widgetDesc}</p>
          </div>
          {!on && (
            <button className="btn btn-auto" disabled={busy || !roomLeft} onClick={turnOn}>{c.turnOn}</button>
          )}
        </div>
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
                onClick={() => update({ color: form.color, position: form.position, mode: form.mode })}>
                {c.save}
              </button>
            </div>
          </>
        )}
      </div>

      <div className="coming-grid">
        {([["whatsapp", c.whatsappDesc, 5], ["instagram", c.instagramDesc, 5], ["email", c.emailDesc, 6]] as const).map(([k, desc, step]) => (
          <div key={k} className="card coming-card">
            <h2 className="channel-title">{t.inbox.channelNames[k]}</h2>
            <p className="hint">{desc}</p>
            <span className="step">{fill(c.comingStep, { n: step })}</span>
          </div>
        ))}
      </div>
    </>
  );
}
