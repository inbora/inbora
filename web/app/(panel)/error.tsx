"use client";

import { useEffect } from "react";
import { reportClientError } from "@/components/ErrorReporter";
import { useI18n } from "@/lib/i18n/client";

/** A page in the panel crashed: tell the user, report it, offer to retry. */
export default function PanelError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const { t } = useI18n();
  useEffect(() => {
    reportClientError(`${error.name}: ${error.message}${error.digest ? ` (digest ${error.digest})` : ""}`, error.stack);
  }, [error]);
  return (
    <div className="card">
      <h2>{t.panel.errorTitle}</h2>
      <p className="hint">{t.panel.errorText}</p>
      <button className="btn btn-sm" onClick={reset}>{t.panel.errorRetry}</button>
    </div>
  );
}
