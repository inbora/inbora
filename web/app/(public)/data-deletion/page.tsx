import DeletionRequest from "@/components/DeletionRequest";

export const metadata = { title: "Data deletion · Inbora" };

export default async function DataDeletionPage({ searchParams }: { searchParams: Promise<{ code?: string }> }) {
  const { code } = await searchParams;
  return (
    <article>
      <h1>Delete your data</h1>
      <p className="updated">For people who sent messages to a business that uses Inbora</p>
      <p>
        Businesses use Inbora to answer messages from their website chat, WhatsApp, Instagram and email. If you messaged
        one of them, your messages and details (such as your name, phone number, Instagram username or email address) may
        be stored in Inbora for that business.
      </p>
      <p>
        You can ask the business directly, or use this form. We’ll delete your conversations, messages, photos and
        details from <b>every</b> business on Inbora, usually within 7 days. It can’t be undone. Deleting your data in
        Inbora doesn’t delete messages on WhatsApp, Instagram or in your own mailbox.
      </p>
      <DeletionRequest initialCode={code} />
      <p className="hint">
        Questions: <a href="mailto:contact@inbora.ai">contact@inbora.ai</a>. Read how we handle data in our{" "}
        <a href="/privacy">Privacy Policy</a>.
      </p>
    </article>
  );
}
