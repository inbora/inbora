import KnowledgeManager, { type Article } from "@/components/KnowledgeManager";
import { apiGet } from "@/lib/api";
import { getI18n } from "@/lib/i18n/server";

export default async function KnowledgePage() {
  const { t } = await getI18n();
  const data = await apiGet<{ articles: Article[]; used: number; limit: number }>("/knowledge");
  return (
    <>
      <h1>{t.knowledge.title}</h1>
      <p className="hint">{t.knowledge.intro}</p>
      {data && <KnowledgeManager initial={data} />}
    </>
  );
}
