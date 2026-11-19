"use client";

import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n/client";
import { LANG_COOKIE, LANG_LABELS, LANGS, type Lang } from "@/lib/i18n/dictionaries";

export default function LanguageSwitcher() {
  const { lang } = useI18n();
  const router = useRouter();

  function change(next: Lang) {
    document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    router.refresh();
  }

  return (
    <select
      className="lang"
      aria-label="Language"
      value={lang}
      onChange={(e) => change(e.target.value as Lang)}
    >
      {LANGS.map((l) => (
        <option key={l} value={l}>
          {LANG_LABELS[l]}
        </option>
      ))}
    </select>
  );
}
