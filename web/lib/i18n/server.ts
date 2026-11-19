import { cookies } from "next/headers";
import { DICTS, isLang, LANG_COOKIE, RTL_LANGS, type Lang } from "./dictionaries";

export async function getLang(): Promise<Lang> {
  const v = (await cookies()).get(LANG_COOKIE)?.value;
  return isLang(v) ? v : "en";
}

export async function getI18n() {
  const lang = await getLang();
  return { lang, t: DICTS[lang], dir: RTL_LANGS.includes(lang) ? "rtl" : "ltr" } as const;
}
