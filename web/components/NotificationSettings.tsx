"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/apiClient";
import { useI18n } from "@/lib/i18n/client";

type State = "loading" | "unsupported" | "blocked" | "off" | "on" | "notConfigured";

function urlB64ToUint8Array(base64: string) {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (ch) => ch.charCodeAt(0));
}

export default function NotificationSettings({ email }: { email: string }) {
  const { t } = useI18n();
  const n = t.notify;
  const [state, setState] = useState<State>("loading");
  const [msg, setMsg] = useState<"" | "testSent" | "error">("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        return setState("unsupported");
      }
      if (Notification.permission === "denied") return setState("blocked");
      const reg = await navigator.serviceWorker.getRegistration("/");
      const sub = await reg?.pushManager.getSubscription();
      setState(sub ? "on" : "off");
    })().catch(() => setState("unsupported"));
  }, []);

  async function enable() {
    setBusy(true);
    setMsg("");
    try {
      let key: string;
      try {
        key = (await api<{ key: string }>("/push/public-key")).key;
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return setState("notConfigured");
        throw e;
      }
      const permission = await Notification.requestPermission();
      if (permission !== "granted") return setState(permission === "denied" ? "blocked" : "off");
      const reg = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
      await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlB64ToUint8Array(key) });
      const json = sub.toJSON();
      await api("/push/subscribe", { method: "POST", body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }) });
      setState("on");
    } catch {
      setMsg("error");
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    setMsg("");
    try {
      const reg = await navigator.serviceWorker.getRegistration("/");
      const sub = await reg?.pushManager.getSubscription();
      if (sub) {
        await api("/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
        await sub.unsubscribe();
      }
      setState("off");
    } catch {
      setMsg("error");
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    setMsg("");
    try {
      await api("/push/test", { method: "POST" });
      setMsg("testSent");
    } catch {
      setMsg("error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <h2>{n.title}</h2>
      <p className="hint">{n.emailInfo.replace("{email}", email)}</p>
      <h3 className="sub-title">{n.pushTitle}</h3>
      <p className="hint">{n.pushDesc}</p>
      {state === "unsupported" && <div className="alert alert-warn">{n.unsupported}</div>}
      {state === "blocked" && <div className="alert alert-warn">{n.blocked}</div>}
      {state === "notConfigured" && <div className="alert alert-warn">{n.notConfigured}</div>}
      <div className="actions actions-start">
        {state === "off" && <button className="btn btn-auto" disabled={busy} onClick={enable}>{n.enable}</button>}
        {state === "on" && (
          <>
            <span className="saved">✓ {n.on}</span>
            <button className="btn btn-secondary btn-auto" disabled={busy} onClick={test}>{n.test}</button>
            <button className="link-btn link-danger" disabled={busy} onClick={disable}>{n.disable}</button>
          </>
        )}
        {msg === "testSent" && <span className="hint">{n.testSent}</span>}
        {msg === "error" && <span className="error-text">{n.error}</span>}
      </div>
    </div>
  );
}
