-- ═══════════════════════════════════════════════════════════════════════
-- Inbora — initial schema (Step 1)
--
-- Run once in the Supabase SQL editor (or `supabase db push`).
-- Every business table carries tenant_id. Row-level security lets a
-- logged-in user see only the tenants they belong to; the backend uses the
-- service_role key, which bypasses RLS, for webhooks and the worker.
-- ═══════════════════════════════════════════════════════════════════════

create extension if not exists pgcrypto;

-- ───────────────────────────────────────────────────────────────────────
-- Platform
-- ───────────────────────────────────────────────────────────────────────

-- Emails that become super-admin when they sign up.
create table public.platform_admins (
  email text primary key
);
insert into public.platform_admins (email) values ('contact@inbora.ai');

-- Plans are data, not code: the super-admin creates and edits them.
create table public.plans (
  id                  uuid primary key default gen_random_uuid(),
  code                text not null unique,                 -- free, starter, growth, pro
  name                text not null,
  price_usd           numeric(10,2) not null default 0,     -- web price
  billing_period      text not null default 'monthly'
                        check (billing_period in ('one_time', 'monthly')),
  conversation_quota  integer not null,                     -- per period (or total for one_time)
  max_channels        integer not null default 4,
  kb_char_limit       integer not null,
  seats               integer not null default 1,
  show_branding       boolean not null default true,        -- "Powered by Inbora"
  is_public           boolean not null default true,        -- shown on the plan page
  is_signup_default   boolean not null default false,       -- given to new tenants
  active              boolean not null default true,
  sort_order          integer not null default 0,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

-- Only one plan can be the signup default.
create unique index plans_one_signup_default
  on public.plans (is_signup_default) where is_signup_default;

insert into public.plans
  (code, name, price_usd, billing_period, conversation_quota, max_channels,
   kb_char_limit, seats, show_branding, is_signup_default, sort_order)
values
  ('free',    'Free',     0, 'one_time',   50, 1,  20000, 1, true,  true,  0),
  ('starter', 'Starter', 14, 'monthly',    50, 4,  50000, 1, true,  false, 1),
  ('growth',  'Growth',  29, 'monthly',   500, 4, 150000, 3, false, false, 2),
  ('pro',     'Pro',     59, 'monthly',  2000, 4, 400000, 5, false, false, 3);

-- ───────────────────────────────────────────────────────────────────────
-- Tenants and users
-- ───────────────────────────────────────────────────────────────────────

create table public.tenants (
  id                 uuid primary key default gen_random_uuid(),
  name               text not null,
  slug               text not null unique,
  default_language   text not null default 'en' check (default_language in ('en', 'he', 'ar')),
  status             text not null default 'active' check (status in ('active', 'suspended')),
  zernio_profile_id  text,
  created_at         timestamptz not null default now()
);

-- One row per auth user.
create table public.profiles (
  id                  uuid primary key references auth.users (id) on delete cascade,
  email               text not null,
  full_name           text,
  is_super_admin      boolean not null default false,
  preferred_language  text not null default 'en' check (preferred_language in ('en', 'he', 'ar')),
  created_at          timestamptz not null default now()
);

create table public.tenant_members (
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  user_id     uuid not null references auth.users (id) on delete cascade,
  role        text not null default 'owner' check (role in ('owner', 'admin', 'agent')),
  created_at  timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index tenant_members_user_idx on public.tenant_members (user_id);

-- ───────────────────────────────────────────────────────────────────────
-- Billing
-- ───────────────────────────────────────────────────────────────────────

-- A subscription keeps a snapshot of the plan's limits at the time it was
-- assigned, so editing a plan never changes existing subscribers.
create table public.subscriptions (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants (id) on delete cascade,
  plan_id       uuid not null references public.plans (id),
  status        text not null default 'active' check (status in ('active', 'canceled', 'expired')),
  limits        jsonb not null,               -- snapshot: quota, channels, kb, seats, branding, period
  period_start  timestamptz not null default now(),
  period_end    timestamptz,                  -- null for one_time plans
  provider      text not null default 'manual',
  provider_ref  text,
  created_at    timestamptz not null default now(),
  canceled_at   timestamptz
);
-- At most one active subscription per tenant.
create unique index subscriptions_one_active
  on public.subscriptions (tenant_id) where status = 'active';

create table public.usage_counters (
  tenant_id            uuid not null references public.tenants (id) on delete cascade,
  period_start         timestamptz not null,
  conversations_used   integer not null default 0,
  bonus_conversations  integer not null default 0,
  primary key (tenant_id, period_start)
);

-- ───────────────────────────────────────────────────────────────────────
-- Channels, contacts, threads, messages
-- ───────────────────────────────────────────────────────────────────────

create table public.channels (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references public.tenants (id) on delete cascade,
  type                 text not null check (type in ('widget', 'whatsapp', 'instagram', 'email')),
  mode                 text not null default 'auto' check (mode in ('auto', 'human')),
  status               text not null default 'pending'
                         check (status in ('pending', 'connected', 'disconnected', 'error')),
  display_name         text,
  external_account_id  text,              -- Zernio account id or Unipile account id
  widget_key           text unique,       -- public key embedded in the site snippet
  config               jsonb not null default '{}'::jsonb,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now()
);
create index channels_tenant_idx on public.channels (tenant_id);
create index channels_external_idx on public.channels (external_account_id);

create table public.contacts (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  channel_id   uuid not null references public.channels (id) on delete cascade,
  external_id  text not null,             -- phone, IG user id, email address, widget visitor id
  name         text,
  email        text,
  phone        text,
  created_at   timestamptz not null default now(),
  unique (channel_id, external_id)
);
create index contacts_tenant_idx on public.contacts (tenant_id);

-- One continuous thread per contact and channel.
create table public.threads (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references public.tenants (id) on delete cascade,
  channel_id            uuid not null references public.channels (id) on delete cascade,
  contact_id            uuid not null references public.contacts (id) on delete cascade,
  status                text not null default 'bot' check (status in ('bot', 'escalated', 'closed')),
  escalation_reason     text,
  unread                boolean not null default false,
  last_message_at       timestamptz not null default now(),
  last_message_preview  text,
  external_thread_id    text,             -- Zernio conversation id / email thread id
  created_at            timestamptz not null default now(),
  unique (channel_id, contact_id)
);
create index threads_tenant_activity_idx on public.threads (tenant_id, last_message_at desc);

create table public.messages (
  id               bigserial primary key,
  tenant_id        uuid not null references public.tenants (id) on delete cascade,
  thread_id        uuid not null references public.threads (id) on delete cascade,
  role             text not null check (role in ('user', 'assistant', 'human', 'system')),
  content          text not null default '',
  attachment_url   text,
  attachment_mime  text,
  external_id      text,                  -- provider message id, for echo / de-dup
  created_at       timestamptz not null default now()
);
create index messages_thread_idx on public.messages (thread_id, id);
create index messages_tenant_idx on public.messages (tenant_id, created_at desc);

-- Billing units: a 24-hour window opened by a customer message.
create table public.conversations (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  thread_id   uuid not null references public.threads (id) on delete cascade,
  started_at  timestamptz not null default now(),
  expires_at  timestamptz not null default (now() + interval '24 hours')
);
create index conversations_thread_idx on public.conversations (thread_id, expires_at desc);
create index conversations_tenant_idx on public.conversations (tenant_id, started_at desc);

-- ───────────────────────────────────────────────────────────────────────
-- Knowledge and agent settings
-- ───────────────────────────────────────────────────────────────────────

create table public.kb_articles (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references public.tenants (id) on delete cascade,
  title       text not null,
  body        text not null default '',
  enabled     boolean not null default true,
  char_count  integer generated always as (char_length(title) + char_length(body)) stored,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index kb_articles_tenant_idx on public.kb_articles (tenant_id);

create table public.agent_settings (
  tenant_id           uuid primary key references public.tenants (id) on delete cascade,
  instructions        text not null default '',
  tone                text not null default 'friendly',
  default_language    text not null default 'en' check (default_language in ('en', 'he', 'ar')),
  greeting            text,
  escalation_message  text,
  updated_at          timestamptz not null default now()
);

-- ───────────────────────────────────────────────────────────────────────
-- Infrastructure (backend only — no RLS policies, service_role access)
-- ───────────────────────────────────────────────────────────────────────

create table public.processed_events (
  provider    text not null,
  event_id    text not null,
  created_at  timestamptz not null default now(),
  primary key (provider, event_id)
);

create table public.jobs (
  id          bigserial primary key,
  tenant_id   uuid references public.tenants (id) on delete cascade,
  kind        text not null,
  payload     jsonb not null default '{}'::jsonb,
  status      text not null default 'queued' check (status in ('queued', 'running', 'done', 'failed')),
  attempts    integer not null default 0,
  run_after   timestamptz not null default now(),
  locked_at   timestamptz,
  last_error  text,
  created_at  timestamptz not null default now()
);
create index jobs_pending_idx on public.jobs (run_after) where status = 'queued';

create table public.push_subscriptions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  endpoint    text not null unique,
  p256dh      text not null,
  auth        text not null,
  created_at  timestamptz not null default now()
);

-- ═══════════════════════════════════════════════════════════════════════
-- Helper functions (security definer so policies can call them safely)
-- ═══════════════════════════════════════════════════════════════════════

create or replace function public.is_super_admin()
returns boolean
language sql stable security definer set search_path = public
as $$
  select coalesce((select is_super_admin from public.profiles where id = auth.uid()), false);
$$;

create or replace function public.is_tenant_member(tid uuid)
returns boolean
language sql stable security definer set search_path = public
as $$
  select exists (
    select 1 from public.tenant_members
    where tenant_id = tid and user_id = auth.uid()
  );
$$;

-- Builds the limits snapshot stored on a subscription.
create or replace function public.plan_limits(p public.plans)
returns jsonb
language sql immutable
as $$
  select jsonb_build_object(
    'plan_code',          p.code,
    'plan_name',          p.name,
    'price_usd',          p.price_usd,
    'billing_period',     p.billing_period,
    'conversation_quota', p.conversation_quota,
    'max_channels',       p.max_channels,
    'kb_char_limit',      p.kb_char_limit,
    'seats',              p.seats,
    'show_branding',      p.show_branding
  );
$$;

-- ═══════════════════════════════════════════════════════════════════════
-- Signup: create profile, tenant, membership, settings and Free plan
-- ═══════════════════════════════════════════════════════════════════════

create or replace function public.handle_new_user()
returns trigger
language plpgsql security definer set search_path = public
as $$
declare
  v_name      text;
  v_lang      text;
  v_base      text;
  v_slug      text;
  v_tenant    uuid;
  v_plan      public.plans;
  v_is_admin  boolean;
begin
  v_is_admin := exists (select 1 from public.platform_admins where lower(email) = lower(new.email));

  v_lang := coalesce(nullif(new.raw_user_meta_data ->> 'language', ''), 'en');
  if v_lang not in ('en', 'he', 'ar') then
    v_lang := 'en';
  end if;

  insert into public.profiles (id, email, full_name, is_super_admin, preferred_language)
  values (new.id, new.email, new.raw_user_meta_data ->> 'full_name', v_is_admin, v_lang);

  v_name := coalesce(nullif(trim(new.raw_user_meta_data ->> 'business_name'), ''),
                     split_part(new.email, '@', 1));

  -- Slug: latin letters and digits only (Hebrew/Arabic names fall back to "shop"),
  -- plus a short random suffix so it is always unique.
  v_base := trim(both '-' from regexp_replace(lower(v_name), '[^a-z0-9]+', '-', 'g'));
  if v_base = '' then
    v_base := 'shop';
  end if;
  v_slug := left(v_base, 40) || '-' || substr(md5(random()::text), 1, 6);

  insert into public.tenants (name, slug, default_language)
  values (v_name, v_slug, v_lang)
  returning id into v_tenant;

  insert into public.tenant_members (tenant_id, user_id, role)
  values (v_tenant, new.id, 'owner');

  insert into public.agent_settings (tenant_id, default_language)
  values (v_tenant, v_lang);

  select * into v_plan from public.plans where is_signup_default and active limit 1;
  if found then
    insert into public.subscriptions (tenant_id, plan_id, limits, period_start, period_end)
    values (
      v_tenant, v_plan.id, public.plan_limits(v_plan), now(),
      case when v_plan.billing_period = 'monthly' then now() + interval '1 month' else null end
    );
    insert into public.usage_counters (tenant_id, period_start)
    values (v_tenant, now());
  end if;

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ═══════════════════════════════════════════════════════════════════════
-- updated_at maintenance
-- ═══════════════════════════════════════════════════════════════════════

create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger plans_touch       before update on public.plans          for each row execute function public.touch_updated_at();
create trigger channels_touch    before update on public.channels       for each row execute function public.touch_updated_at();
create trigger kb_articles_touch before update on public.kb_articles    for each row execute function public.touch_updated_at();
create trigger agent_set_touch   before update on public.agent_settings for each row execute function public.touch_updated_at();

-- ═══════════════════════════════════════════════════════════════════════
-- Row-level security
-- ═══════════════════════════════════════════════════════════════════════

alter table public.platform_admins     enable row level security;
alter table public.plans               enable row level security;
alter table public.tenants             enable row level security;
alter table public.profiles            enable row level security;
alter table public.tenant_members      enable row level security;
alter table public.subscriptions       enable row level security;
alter table public.usage_counters      enable row level security;
alter table public.channels            enable row level security;
alter table public.contacts            enable row level security;
alter table public.threads             enable row level security;
alter table public.messages            enable row level security;
alter table public.conversations       enable row level security;
alter table public.kb_articles         enable row level security;
alter table public.agent_settings      enable row level security;
alter table public.processed_events    enable row level security;
alter table public.jobs                enable row level security;
alter table public.push_subscriptions  enable row level security;

-- Plans: everyone logged in can read active public plans; super-admin manages all.
create policy plans_read on public.plans
  for select to authenticated
  using ((active and is_public) or public.is_super_admin());
create policy plans_admin on public.plans
  for all to authenticated
  using (public.is_super_admin()) with check (public.is_super_admin());

-- Profiles: own row (read/update), super-admin reads all.
create policy profiles_self_read on public.profiles
  for select to authenticated
  using (id = auth.uid() or public.is_super_admin());
create policy profiles_self_update on public.profiles
  for update to authenticated
  using (id = auth.uid())
  -- a user can never flip their own super-admin flag
  with check (id = auth.uid() and is_super_admin = public.is_super_admin());

-- Tenants: members read and rename; super-admin all.
create policy tenants_member_read on public.tenants
  for select to authenticated
  using (public.is_tenant_member(id) or public.is_super_admin());
create policy tenants_member_update on public.tenants
  for update to authenticated
  using (public.is_tenant_member(id)) with check (public.is_tenant_member(id));
create policy tenants_admin on public.tenants
  for all to authenticated
  using (public.is_super_admin()) with check (public.is_super_admin());

-- Memberships: see your own tenants' members.
create policy members_read on public.tenant_members
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());

-- Billing tables: members read only; changes go through the backend.
create policy subscriptions_read on public.subscriptions
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());
create policy usage_read on public.usage_counters
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());

-- Tenant-owned data: members have full access to their own tenant's rows.
do $$
declare t text;
begin
  foreach t in array array['channels', 'contacts', 'threads', 'messages',
                           'conversations', 'kb_articles', 'agent_settings']
  loop
    execute format(
      'create policy %I on public.%I for all to authenticated
         using (public.is_tenant_member(tenant_id) or public.is_super_admin())
         with check (public.is_tenant_member(tenant_id) or public.is_super_admin());',
      t || '_member_all', t);
  end loop;
end $$;

-- Conversations are billing units: members may read but not create or delete them.
drop policy conversations_member_all on public.conversations;
create policy conversations_read on public.conversations
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());

-- Push subscriptions: each user manages their own.
create policy push_self on public.push_subscriptions
  for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- platform_admins, processed_events, jobs: no policies → backend (service_role) only.
