# Inbora

AI customer service for WhatsApp, Instagram, email and websites — one agent,
many businesses.

| Folder | What it is | Runs on |
| --- | --- | --- |
| `backend/` | FastAPI API (and, from Step 2, the worker) | Render, `inbora-api` |
| `web/` | Next.js control panel + super-admin | Render, `inbora-web` |
| `supabase/migrations/` | Database schema, security rules, plans | Supabase |

**Step 1 is done when:** you sign up at `https://app.inbora.ai`, land in an
empty panel showing your business on the Free plan, and can switch the panel
to Hebrew or Arabic. Signing up with `contact@inbora.ai` also shows the
Super-admin page.

---

## Setup (about an hour, in this order)

### 1. Supabase

1. Create a new project. Region: **Frankfurt (eu-central-1)**.
2. **SQL Editor → New query** → paste all of `supabase/migrations/0001_init.sql` → **Run**.
   You should see the tables under Table Editor and four rows in `plans`.
3. **Authentication → URL Configuration**
   - Site URL: `https://app.inbora.ai`
   - Redirect URLs: add `https://app.inbora.ai/**` and `http://localhost:3000/**`
4. **Authentication → Emails → Templates** — change the link in two templates so
   confirmation works even if the email is opened on another device:
   - *Confirm signup*: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email&next=/inbox`
   - *Reset password*: `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=recovery&next=/reset-password`
5. **Authentication → Emails → SMTP Settings** — Supabase's built-in sender only
   allows a few emails per hour, so send through Resend instead:
   host `smtp.resend.com`, port `465`, username `resend`, password = a Resend
   API key, sender `no-reply@inbora.ai`, name `Inbora`.
   (Needs `inbora.ai` verified in Resend first — see step 4 below.)
6. Copy these for later (**Project Settings → Data API** and **API Keys**):
   project URL, anon / publishable key, service_role / secret key.
   If **Project Settings → JWT Keys** shows only a "Legacy JWT secret", copy that too.

### 2. GitHub

    cd inbora
    git init && git add . && git commit -m "Step 1: foundation"
    git branch -M main
    git remote add origin git@github.com:YOUR-USER/inbora.git
    git push -u origin main

### 3. Render

1. **New → Blueprint** → pick the `inbora` repo. Render reads `render.yaml`
   and creates `inbora-api` and `inbora-web`.
2. Fill in the secrets it asks for:
   - `inbora-api`: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
     `SUPABASE_JWT_SECRET` (only if you have a legacy secret, else leave empty),
     `GEMINI_API_KEY` (can wait until Step 2)
   - `inbora-web`: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. On each service → **Settings → Custom Domains**:
   `api.inbora.ai` on `inbora-api`, `app.inbora.ai` on `inbora-web`.
   Render shows a CNAME target for each.

### 4. DNS for inbora.ai (at your domain registrar)

- `api` → CNAME → the target Render showed for `inbora-api`
- `app` → CNAME → the target Render showed for `inbora-web`
- **Resend → Domains → Add `inbora.ai`** → add the records it lists
  (SPF/DKIM/MX for the sending subdomain). Verification can take a few hours.

When the domains are live, open `https://api.inbora.ai/health` — it should
return `{"status":"ok","database":"ok"}`.

### 5. Become super-admin

Sign up at `https://app.inbora.ai/signup` with **contact@inbora.ai**.
The database marks that email as super-admin automatically (the list lives in
the `platform_admins` table). Every account, including yours, also gets its
own business on the Free plan.

---

## Step 2 — agent core

The agent answers from each business's own instructions and knowledge
articles, using Gemini with the same model fallback as the Grinta agent.
Incoming messages are stored first and answered by a background worker,
which runs inside the API process for now (no extra Render service).

**Setup**

1. Supabase → SQL Editor → run `supabase/migrations/0002_agent_core.sql`.
2. Google AI Studio → create an API key → on Render, `inbora-api` →
   Environment → `GEMINI_API_KEY`.
3. Push to GitHub; Render deploys. `/health` should show `"agent":"ok"`.

**Try it:** open the **Agent** page in the panel and chat with the test box.
Until Step 3 adds the Knowledge page, add articles in Supabase →
Table Editor → `kb_articles` (or with the SQL in the Step 2 notes).

**Pieces**

| File | What it does |
| --- | --- |
| `backend/app/agent/prompt.py` | Base rules + the business's instructions + its articles |
| `backend/app/agent/loop.py` | Gemini tool loop, reasoning stripping, raw-output guard |
| `backend/app/agent/tools.py` | `escalate_to_human`, `collect_contact_email` |
| `backend/app/inbound.py` | Every incoming message: store it, queue a reply |
| `backend/app/worker_loop.py` | Takes queued jobs, answers, retries 3 times |
| `backend/app/routers/agent.py` | `POST /agent/test` for the panel's test chat (writes nothing) |

- **Newest message wins:** each customer message bumps `threads.reply_epoch`;
  a reply written for an older epoch is thrown away, so quick bursts get one
  answer. Replies wait 2 seconds for follow-up messages.
- **Human takeover:** while a thread is `escalated`, or its channel is in
  human mode, the agent stays quiet.
- **Failures:** a reply job is retried after 5 s and 30 s; if every attempt
  fails, the thread is handed to the team instead of leaving the customer
  waiting.
- **Separate worker later:** set `EMBEDDED_WORKER=false` on the API and run
  `python worker.py` as a Render background worker.

## Step 3 — knowledge and agent settings

**Setup:** Supabase → SQL Editor → run `supabase/migrations/0003_knowledge.sql`.

- **Knowledge page:** write, edit, switch on/off and delete articles. Only
  switched-on articles count toward the plan's character limit and reach the
  agent; switched-off ones are drafts. Templates (shipping, returns, payment,
  contact, opening hours — in English, Hebrew or Arabic) are added switched
  off, because their [brackets] must be filled in first.
- **Agent page:** instructions, tone, default language and website
  greeting, next to the test chat. Changes apply to the next message right away.
- Articles and settings are changed only through the API
  (`/knowledge`, `/agent/settings`), which enforces the limit; the database
  lets the browser read them but not write them.

## Step 4 — website chat, inbox and alerts

**Setup:**
1. Supabase → SQL Editor → run `supabase/migrations/0004_inbox_widget.sql`.
2. Render → inbora-api → Environment: add `RESEND_API_KEY` (Resend → API Keys,
   with inbora.ai verified as a sending domain), `VAPID_PUBLIC_KEY` and
   `VAPID_PRIVATE_KEY` (one pair for good: `npx web-push generate-vapid-keys`).
   Optional: `ALERTS_FROM` (default `Inbora <alerts@inbora.ai>`), `APP_URL`
   (default `https://app.inbora.ai`, used in alert links), `HANDBACK_HOURS`
   (default 1).

- **Website chat (Channels page):** one per business. Turn it on, copy the
  one-line snippet into the site, pick a colour and side, and choose who
  answers (agent with team takeover, or team only). "Open test page" shows the
  chat on a blank page served by the API (`/widget/<key>/demo`).
- **Widget** (`backend/app/static/widget.js`, served at `/widget/widget.js`):
  self-contained, Shadow DOM so the site's CSS can't break it, English /
  Hebrew / Arabic with right-to-left, polls for replies (every 2–5 s while
  open), typing dots, team replies labelled, "Powered by Inbora" when the
  plan has branding. Visitors get a random id kept in the browser. Public
  endpoints are rate-limited (per visitor, per IP, per chat) and accept CORS
  from any site; the rest of the API only from `WEB_URL`.
- **Inbox:** all conversations, newest first, with filters (all / needs you, channel,
  date range) and search over names,
  emails, phones and message text. A conversation shows who wrote each reply.
  - **Reply** — sends as the team; the team now owns the conversation and the
    agent stays quiet. A reply the agent was about to send is dropped.
  - **Take over / Hand back** — handing back makes the agent answer the
    customer's last message if it's still unanswered.
  - **Auto hand-back** — if the team hasn't written for `HANDBACK_HOURS` and the
    customer writes again, the agent takes the conversation back.
  - **AI draft** — the agent writes a reply as the team (with an optional
    direction, e.g. "offer a 10% coupon"); you edit it and send. Nothing is
    sent or saved until you press Send.
- **Alerts:** when a conversation is escalated (by the agent, by a technical
  failure, or a new message in a team-only chat) every team member gets an
  email (Resend) and a browser notification (Settings → Notifications → turn
  on for this device). A customer who keeps writing while the team handles
  the conversation triggers at most one alert per 10 minutes, until the team
  replies. Alerts run as background jobs, so a slow email never delays a
  reply.
- **Contact details (Agent page):** before passing a website visitor to the
  team, the agent asks for their email, phone, either, or nothing (the team
  then answers in the chat). On WhatsApp, Instagram and email it never asks.

---

## Run locally

    # API
    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # fill in the Supabase values
    uvicorn app.main:app --reload --port 8000

    # Panel (second terminal)
    cd web
    npm install
    cp .env.example .env.local  # fill in the Supabase values
    npm run dev                 # http://localhost:3000

---

## How it fits together

- **Signup** — the panel calls Supabase Auth with the business name. A database
  trigger (`handle_new_user`) creates the profile, the business, the owner
  membership, default agent settings and an active Free subscription.
- **Security** — every table has row-level security: a logged-in user can only
  read and change their own business's rows, cannot change their plan, and
  cannot make themselves super-admin. The API uses the service_role key and
  filters by business itself.
- **Plans** — stored in the `plans` table. A subscription keeps a snapshot of
  the plan's limits (`subscriptions.limits`), so editing a plan later never
  changes what existing subscribers have.
- **API auth** — the panel sends the Supabase access token; the API verifies it
  (JWKS signing keys, or the legacy HS256 secret) and loads the user's profile.
- **Languages** — English, Hebrew, Arabic. The choice is a cookie (`inb_lang`);
  Hebrew and Arabic switch the whole layout to right-to-left.

## Notes

- Render free instances sleep after ~15 minutes idle; the first request then
  takes up to a minute. Move both services to a paid plan before beta
  (webhooks from Step 5 need the API always awake).
- `NEXT_PUBLIC_*` variables are baked in at build time: after changing them on
  Render, use **Manual Deploy → Clear build cache & deploy**.
