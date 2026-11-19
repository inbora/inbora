"use client";

import { createContext, useContext } from "react";
import { DICTS, type Dict, type Lang } from "./dictionaries";

const I18nContext = createContext<{ lang: Lang; t: Dict }>({ lang: "en", t: DICTS.en });

export function I18nProvider({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  return <I18nContext.Provider value={{ lang, t: DICTS[lang] }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
