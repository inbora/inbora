import Link from "next/link";

export const metadata = { title: "Privacy Policy · Inbora" };

export default function PrivacyPage() {
  return (
    <article>
      <h1>Privacy Policy</h1>
      <p className="updated">Last updated: November 20, 2026</p>

      <p>
        Inbora (inbora.ai) gives businesses an AI customer-service agent and a shared inbox. This policy explains what
        personal data we handle and why. It covers two groups of people: <b>businesses</b> that use Inbora and their team
        members, and <b>their customers</b> who send messages to those businesses. Inbora is operated from Israel; contact
        us at <a href="mailto:contact@inbora.ai">contact@inbora.ai</a>.
      </p>

      <h2>1. Our role</h2>
      <ul>
        <li>For a business’s own account (its team’s names, emails and settings) we decide how the data is used.</li>
        <li>For the messages and details of a business’s customers, the <b>business</b> decides how they are used, and
          Inbora processes them on the business’s behalf. If you messaged a business, that business’s own privacy notice
          applies too, and you can contact it directly.</li>
      </ul>

      <h2>2. What we collect</h2>
      <ul>
        <li><b>Business accounts:</b> name and email of each team member, business name, language, settings, the
          knowledge articles and agent instructions the business writes, plan and usage.</li>
        <li><b>Customers’ messages:</b> the messages, photos and attachments sent to the business on its website chat,
          WhatsApp, Instagram or email, the replies, and the details those channels provide, such as name, phone number,
          Instagram username or email address, and the subject of emails.</li>
        <li><b>Connected channels:</b> the identifiers and access needed to receive and send messages for the business
          (for example its WhatsApp number, Instagram account or mailbox). Passwords for mailboxes are passed to our
          provider to connect the mailbox and are not stored by Inbora.</li>
        <li><b>Technical data:</b> logs of errors and requests, and a random identifier the website chat keeps in the
          visitor’s browser so the conversation continues across pages.</li>
      </ul>

      <h2>3. How we use it</h2>
      <ul>
        <li>To show conversations in the business’s inbox and let its team reply.</li>
        <li>When the business turns it on, to have the AI agent read the conversation and the business’s knowledge and
          write an answer. Messages are sent to our AI provider only to produce that answer; they are not used to train
          AI models.</li>
        <li>To send the business alerts (email and push notifications), to count usage for its plan, to keep the service
          secure and working, and to fix errors.</li>
        <li>We don’t sell personal data and don’t use customers’ messages for advertising.</li>
      </ul>

      <h2>4. Service providers</h2>
      <p>We use these providers to run Inbora. Each processes data only to provide its service to us:</p>
      <ul>
        <li><b>Supabase</b> — database, login and file storage.</li>
        <li><b>Render</b> — hosting of the Inbora servers.</li>
        <li><b>Google (Gemini API)</b> — the AI model that writes answers and drafts.</li>
        <li><b>Zernio</b> — connection to WhatsApp, Instagram and email mailboxes.</li>
        <li><b>Meta, Google, Microsoft and other email providers</b> — the platforms that deliver the messages.</li>
        <li><b>Resend</b> — sending alert emails to businesses.</li>
      </ul>
      <p>
        These providers may process data outside Israel (for example in the United States or the European Union), with
        the safeguards they offer for international transfers.
      </p>

      <h2>5. Google user data</h2>
      <p>
        When a business connects a Gmail or Google Workspace mailbox, Inbora reads and sends email in that mailbox only to
        show customer emails in the business’s inbox and send its replies. Inbora’s use and transfer of information
        received from Google APIs adheres to the{" "}
        <a href="https://developers.google.com/terms/api-services-user-data-policy" target="_blank" rel="noreferrer">
          Google API Services User Data Policy
        </a>, including the Limited Use requirements. We don’t use this data for advertising, don’t sell it, and don’t let
        people read it except with the business’s permission, for security, or where the law requires it.
      </p>

      <h2>6. How long we keep data</h2>
      <ul>
        <li>Conversations stay until the business deletes them or closes its account. Businesses can delete a
          conversation at any time from their inbox; deleting removes its messages, photos and the customer’s details.</li>
        <li>When a business closes its account, we delete its data within 30 days.</li>
        <li>Error and request logs are kept for a limited time, normally up to 90 days.</li>
      </ul>

      <h2>7. Your rights</h2>
      <p>
        Depending on where you live, you can ask to access, correct or delete your personal data, or object to how it is
        used. If you sent messages to a business that uses Inbora, you can ask that business, or ask us through our{" "}
        <Link href="/data-deletion">data deletion page</Link> and we will delete your conversations and details from every
        business on Inbora. Businesses and team members can write to{" "}
        <a href="mailto:contact@inbora.ai">contact@inbora.ai</a>. You may also complain to your data-protection authority
        (in Israel, the Privacy Protection Authority).
      </p>

      <h2>8. Security</h2>
      <p>
        Data is sent over encrypted connections, access is limited by business so one business can’t see another’s data,
        and only people who need it to run the service can access it. No system is perfectly secure; if a breach affects
        your data we will tell the affected businesses as the law requires.
      </p>

      <h2>9. Children</h2>
      <p>Inbora is for businesses and is not directed at children. Accounts are for people aged 18 or older.</p>

      <h2>10. Changes</h2>
      <p>
        We may update this policy. We’ll post the new version here with its date and, for important changes, tell
        businesses by email or in the panel.
      </p>
    </article>
  );
}
