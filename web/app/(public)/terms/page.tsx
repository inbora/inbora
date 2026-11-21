import Link from "next/link";

export const metadata = { title: "Terms of Service · Inbora" };

export default function TermsPage() {
  return (
    <article>
      <h1>Terms of Service</h1>
      <p className="updated">Last updated: November 20, 2026</p>

      <p>
        These terms apply to Inbora (inbora.ai), a service that gives businesses an AI customer-service agent and a
        shared inbox for their website chat, WhatsApp, Instagram and email. Inbora is operated from Israel
        (“Inbora”, “we”). By creating an account or using Inbora you agree to these terms on behalf of your business
        (“you”). If you don’t agree, don’t use Inbora.
      </p>

      <h2>1. Your account</h2>
      <ul>
        <li>You must give accurate information and keep your login details safe. You are responsible for everything done
          with your account, including by team members you invite.</li>
        <li>You must be at least 18 and allowed to act for the business you sign up.</li>
        <li>Tell us right away at <a href="mailto:contact@inbora.ai">contact@inbora.ai</a> if you think your account was
          used without permission.</li>
      </ul>

      <h2>2. What Inbora does</h2>
      <ul>
        <li>Inbora receives messages your customers send you on the channels you connect, shows them in your inbox, and,
          when you turn it on, answers them with an AI agent using the knowledge and instructions you give it.</li>
        <li>WhatsApp, Instagram and email are connected through our provider Zernio and the platforms themselves (Meta,
          Google, Microsoft and others). Their rules and availability are outside our control; a channel can stop working
          if a platform changes or blocks access.</li>
        <li>We may improve, change or remove features. We’ll tell you in advance about changes that significantly reduce
          what your plan includes.</li>
      </ul>

      <h2>3. AI answers</h2>
      <ul>
        <li>AI can be wrong. It answers from the knowledge and instructions you provide, and may still make mistakes or
          misunderstand a customer. You are responsible for the content you give it, for checking how it answers, and for
          the replies sent to your customers in your name.</li>
        <li>Don’t use Inbora for decisions that need a qualified professional (for example medical, legal or financial
          advice) without a person checking the answer.</li>
      </ul>

      <h2>4. Your responsibilities</h2>
      <ul>
        <li>You may only message people who contacted you or agreed to hear from you, and you must follow the laws that
          apply to you (including privacy, consumer-protection and anti-spam laws) and the policies of each platform you
          connect, such as the WhatsApp Business and Meta platform policies.</li>
        <li>Don’t use Inbora to send spam, unlawful, misleading, harmful or infringing content, to impersonate others, or
          to try to break, overload or get around the security or limits of the service.</li>
        <li>You are responsible for telling your customers, in your own privacy notice, that you use Inbora and AI to
          handle their messages.</li>
      </ul>

      <h2>5. Your data</h2>
      <ul>
        <li>The content you and your customers put into Inbora (messages, contact details, photos, knowledge articles)
          belongs to you or them. You give us permission to store and process it only to provide and improve the service
          for you, as described in our <Link href="/privacy">Privacy Policy</Link>.</li>
        <li>For your customers’ personal data, you are the controller and we process it on your behalf and on your
          instructions.</li>
        <li>You can export or delete conversations from your inbox. When your account is closed we delete your data
          within 30 days, except where we must keep something by law.</li>
      </ul>

      <h2>6. Plans, limits and payment</h2>
      <ul>
        <li>Each plan has limits (for example AI conversations, channels, knowledge size and team members), shown on your
          Plan page. AI conversations include the agent&apos;s answers and replies your team writes with AI. When the
          limit is reached, the AI stops answering new conversations until the next period or an upgrade; your team
          still receives them. Conversations your team handles without AI are not limited, subject to fair use.</li>
        <li>New businesses start with a free trial that ends after 14 days or 50 AI conversations, whichever comes
          first. After the trial, the AI pauses until you choose a plan. Paid plans are billed per month in advance at
          the price shown when you subscribe. Until online payment is available, plan changes are arranged with us
          directly.</li>
        <li>We may change prices or plans for new subscribers. Your current plan keeps its terms until you change or
          cancel it; if we must change the price of an existing plan, we will tell you at least 30 days before.</li>
        <li>Fees already paid are not refunded, except where the law requires it.</li>
      </ul>

      <h2>7. Suspension and ending</h2>
      <ul>
        <li>You can stop using Inbora at any time by contacting us to close your account.</li>
        <li>We may suspend or close an account that breaks these terms, puts the service or others at risk, or is
          unpaid. Where possible we’ll warn you first and give you a chance to fix the problem.</li>
      </ul>

      <h2>8. Liability</h2>
      <ul>
        <li>Inbora is provided “as is”. We work to keep it available and secure, but we don’t promise it will be
          uninterrupted or error-free, or that AI answers will always be correct.</li>
        <li>To the extent the law allows, we are not liable for indirect or consequential losses (such as lost profits,
          lost sales or lost data), and our total liability for any claim is limited to the amount you paid us in the 12
          months before the claim.</li>
        <li>You will cover our reasonable costs if a claim is made against us because of content you or your customers
          send through Inbora, or your breach of these terms or of a platform’s policies.</li>
      </ul>

      <h2>9. Changes to these terms</h2>
      <p>
        We may update these terms. We’ll post the new version here and, for important changes, tell you by email or in
        the panel at least 14 days before they apply. Continuing to use Inbora after that means you accept them.
      </p>

      <h2>10. Law and contact</h2>
      <p>
        These terms are governed by the laws of the State of Israel, and the competent courts in Israel have exclusive
        jurisdiction. Questions: <a href="mailto:contact@inbora.ai">contact@inbora.ai</a>.
      </p>
    </article>
  );
}
