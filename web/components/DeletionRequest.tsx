"use client";

import { useEffect, useState } from "react";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const STATUS: Record<string, string> = {
  open: "Received — we're working on it.",
  done: "Done — your data has been deleted.",
  dismissed: "Closed — we couldn't match it to any data, or it needed more details. Email us if you have questions.",
};

/** The public data-deletion form, and a status check by request code. */
export default function DeletionRequest({ initialCode }: { initialCode?: string }) {
  const [contact, setContact] = useState("");
  const [name, setName] = useState("");
  const [business, setBusiness] = useState("");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [code, setCode] = useState(initialCode?.toUpperCase() ?? "");
  const [status, setStatus] = useState<string | null>(null);
  const [checkCode, setCheckCode] = useState(initialCode ?? "");

  async function check(c: string) {
    setError("");
    try {
      const res = await fetch(`${API_URL}/public/data-deletion/${encodeURIComponent(c.trim())}`);
      if (!res.ok) throw new Error(String(res.status));
      setStatus((await res.json()).status);
      setCode(c.trim().toUpperCase());
    } catch {
      setStatus(null);
      setError("We couldn't find a request with that code.");
    }
  }
  useEffect(() => { if (initialCode) check(initialCode); }, [initialCode]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${API_URL}/public/data-deletion`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contact, name: name || null, business: business || null, details: details || null }),
      });
      if (res.status === 429) throw new Error("rate");
      if (!res.ok) throw new Error(String(res.status));
      const r = await res.json();
      setCode(r.code);
      setStatus("open");
      window.history.replaceState(null, "", `/data-deletion?code=${r.code}`);
    } catch (err) {
      setError(err instanceof Error && err.message === "rate"
        ? "Too many requests from here. Please try again in an hour."
        : "Something went wrong. Please try again, or email contact@inbora.ai.");
    } finally {
      setBusy(false);
    }
  }

  if (code && status) {
    return (
      <div className="card deletion-done">
        <h2>Request {code}</h2>
        <p className="deletion-status"><b>{STATUS[status] ?? status}</b></p>
        <p className="hint">Keep this code to check the status later: inbora.ai/data-deletion?code={code}</p>
      </div>
    );
  }

  return (
    <>
      <form className="card" onSubmit={submit}>
        <h2>Request deletion</h2>
        <div className="field">
          <label htmlFor="dd-contact">Your email, phone number or Instagram username *</label>
          <input id="dd-contact" required minLength={3} maxLength={200} value={contact} onChange={(e) => setContact(e.target.value)}
            placeholder="e.g. dana@mail.com, +972 50 123 4567 or @dana" />
          <span className="hint">The one you used when you messaged the business. Add more in the details if you used several.</span>
        </div>
        <div className="field">
          <label htmlFor="dd-name">Your name</label>
          <input id="dd-name" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="dd-business">Which business did you message?</label>
          <input id="dd-business" maxLength={200} value={business} onChange={(e) => setBusiness(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="dd-details">Details</label>
          <textarea id="dd-details" rows={3} maxLength={2000} value={details} onChange={(e) => setDetails(e.target.value)} />
        </div>
        {error && <p className="error-text">{error}</p>}
        <div className="actions"><button className="btn" disabled={busy || contact.trim().length < 3}>{busy ? "Sending…" : "Send request"}</button></div>
      </form>
      <form className="card deletion-check" onSubmit={(e) => { e.preventDefault(); if (checkCode.trim()) check(checkCode); }}>
        <label htmlFor="dd-code">Already sent a request? Check its status</label>
        <div className="check-row">
          <input id="dd-code" maxLength={16} value={checkCode} onChange={(e) => setCheckCode(e.target.value)} placeholder="Request code" />
          <button className="btn btn-secondary">Check</button>
        </div>
      </form>
    </>
  );
}
