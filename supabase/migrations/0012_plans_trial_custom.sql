-- ═══════════════════════════════════════════════════════════════════════
-- New plans (Starter / Business / Pro), a 14-day trial for new businesses,
-- and Custom plans offered by the super-admin. Safe to run again.
--
-- Businesses already on a plan keep what they subscribed with (snapshot).
-- ═══════════════════════════════════════════════════════════════════════

-- ── Trial: a plan that ends after some days (or when its conversations run out)

alter table public.plans drop constraint if exists plans_billing_period_check;
alter table public.plans add constraint plans_billing_period_check
  check (billing_period in ('one_time', 'monthly', 'trial'));
alter table public.plans add column if not exists trial_days integer;

-- The limits snapshot also keeps the trial length.
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
    'show_branding',      p.show_branding,
    'trial_days',         p.trial_days
  );
$$;

-- When a subscription's period ends: a month for monthly plans, the trial
-- length for a trial, never for one-time plans.
create or replace function public.plan_period_end(p public.plans, p_start timestamptz)
returns timestamptz
language sql immutable
as $$
  select case p.billing_period
           when 'monthly' then p_start + interval '1 month'
           when 'trial'   then p_start + make_interval(days => coalesce(p.trial_days, 14))
           else null
         end;
$$;

-- ── The plans

-- Old plans: no longer offered (businesses on them keep their terms).
update public.plans set is_signup_default = false
 where code in ('free', 'growth') and is_signup_default;
update public.plans set is_public = false, active = false, updated_at = now()
 where code in ('free', 'growth');

insert into public.plans
  (code, name, price_usd, billing_period, conversation_quota, max_channels, kb_char_limit, seats,
   show_branding, is_public, is_signup_default, active, sort_order, trial_days)
values
  ('starter',  'Starter',  29, 'monthly',  100, 2,  15000,  1, true,  true,  false, true, 1, null),
  ('business', 'Business', 49, 'monthly',  500, 4,  50000,  5, false, true,  false, true, 2, null),
  ('pro',      'Pro',      89, 'monthly', 2000, 4, 100000, 10, false, true,  false, true, 3, null)
on conflict (code) do update set
  name = excluded.name, price_usd = excluded.price_usd, billing_period = excluded.billing_period,
  conversation_quota = excluded.conversation_quota, max_channels = excluded.max_channels,
  kb_char_limit = excluded.kb_char_limit, seats = excluded.seats, show_branding = excluded.show_branding,
  is_public = true, active = true, sort_order = excluded.sort_order, updated_at = now();

-- The trial: everything in Business, 50 conversations, 14 days. Not on the
-- Plan page; every new business starts on it.
update public.plans set is_signup_default = false where is_signup_default and code <> 'trial';
insert into public.plans
  (code, name, price_usd, billing_period, conversation_quota, max_channels, kb_char_limit, seats,
   show_branding, is_public, is_signup_default, active, sort_order, trial_days)
values ('trial', 'Trial', 0, 'trial', 50, 4, 50000, 5, false, false, true, true, 0, 14)
on conflict (code) do update set is_signup_default = true, active = true, is_public = false;

-- ── Signup and plan changes use the period end above

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
      v_tenant, v_plan.id, public.plan_limits(v_plan), now(), public.plan_period_end(v_plan, now())
    );
    insert into public.usage_counters (tenant_id, period_start)
    values (v_tenant, now());
  end if;

  return new;
end;
$$;

create or replace function public.assign_plan(p_tenant uuid, p_plan uuid, p_provider text default 'manual',
                                              p_ref text default null)
returns uuid
language plpgsql security definer set search_path = public
as $$
declare
  v_plan public.plans;
  v_sub  uuid;
  v_now  timestamptz := clock_timestamp();
begin
  select * into v_plan from public.plans where id = p_plan;
  if not found then
    raise exception 'plan not found';
  end if;
  update public.subscriptions set status = 'canceled', canceled_at = v_now
   where tenant_id = p_tenant and status = 'active';
  insert into public.subscriptions (tenant_id, plan_id, limits, period_start, period_end, provider, provider_ref)
  values (p_tenant, p_plan, public.plan_limits(v_plan), v_now, public.plan_period_end(v_plan, v_now),
          p_provider, p_ref)
  returning id into v_sub;
  insert into public.usage_counters (tenant_id, period_start) values (p_tenant, v_now) on conflict do nothing;
  update public.upgrade_requests set status = 'done', resolved_at = v_now
   where tenant_id = p_tenant and status = 'open';
  return v_sub;
end;
$$;

-- ── The current period: monthly plans move forward; a trial that has ended
-- has no conversations left (the AI pauses until a plan is chosen).

create or replace function public.current_usage(p_tenant uuid)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  s public.subscriptions;
  u public.usage_counters;
  v_trial_ended boolean := false;
begin
  select * into s from public.subscriptions
   where tenant_id = p_tenant and status = 'active' for update;
  if not found then
    return jsonb_build_object('status', 'no_plan');
  end if;
  if s.period_end is not null and now() >= s.period_end then
    if coalesce(s.limits ->> 'billing_period', 'monthly') = 'monthly' then
      while now() >= s.period_end loop
        s.period_start := s.period_end;
        s.period_end := s.period_end + interval '1 month';
      end loop;
      update public.subscriptions set period_start = s.period_start, period_end = s.period_end where id = s.id;
    else
      v_trial_ended := true;
    end if;
  end if;
  insert into public.usage_counters (tenant_id, period_start) values (p_tenant, s.period_start)
  on conflict do nothing;
  select * into u from public.usage_counters where tenant_id = p_tenant and period_start = s.period_start;
  return jsonb_build_object(
    'status', 'ok',
    'period_start', s.period_start,
    'period_end', s.period_end,
    'used', u.conversations_used,
    'trial_ended', v_trial_ended,
    'quota', case when v_trial_ended then 0
                  else coalesce((s.limits ->> 'conversation_quota')::int, 0) + u.bonus_conversations end);
end;
$$;

-- Same as before, except: after a trial ends, no "conversations used up"
-- alert is sent (the panel says the trial ended instead).
create or replace function public.consume_conversation(p_tenant uuid, p_thread uuid)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  cur    jsonb;
  v_used int;
  v_quota int;
  u      public.usage_counters;
  v_alert int := null;
begin
  cur := public.current_usage(p_tenant);            -- also locks the subscription row
  if cur ->> 'status' = 'no_plan' then
    return cur;
  end if;
  if exists (select 1 from public.conversations where thread_id = p_thread and expires_at > now()) then
    return cur || jsonb_build_object('status', 'existing');
  end if;
  if (cur ->> 'trial_ended')::boolean then
    return cur || jsonb_build_object('status', 'over', 'alert', null);
  end if;
  v_quota := (cur ->> 'quota')::int;
  select * into u from public.usage_counters
   where tenant_id = p_tenant and period_start = (cur ->> 'period_start')::timestamptz for update;
  if u.conversations_used >= v_quota then
    if u.alert_100_at is null then
      update public.usage_counters set alert_100_at = now()
       where tenant_id = p_tenant and period_start = u.period_start;
      v_alert := 100;
    end if;
    return cur || jsonb_build_object('status', 'over', 'alert', v_alert);
  end if;
  insert into public.conversations (tenant_id, thread_id) values (p_tenant, p_thread);
  v_used := u.conversations_used + 1;
  if v_used >= v_quota and u.alert_100_at is null then
    v_alert := 100;
  elsif v_used * 5 >= v_quota * 4 and u.alert_80_at is null then
    v_alert := 80;
  end if;
  update public.usage_counters
     set conversations_used = v_used,
         alert_80_at  = case when v_alert is not null then coalesce(alert_80_at, now()) else alert_80_at end,
         alert_100_at = case when v_alert = 100 then now() else alert_100_at end
   where tenant_id = p_tenant and period_start = u.period_start;
  return cur || jsonb_build_object('status', 'new', 'used', v_used, 'alert', v_alert);
end;
$$;

-- ── Custom plans: the business says what it needs, the super-admin sends a
-- price, the business accepts (a private plan is made for it).

create table if not exists public.custom_requests (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references public.tenants (id) on delete cascade,
  requested_by      uuid references auth.users (id) on delete set null,
  conversations     integer not null check (conversations between 1 and 1000000),
  kb_chars          integer not null check (kb_chars between 1000 and 5000000),
  seats             integer not null check (seats between 1 and 1000),
  notes             text check (char_length(notes) <= 2000),
  status            text not null default 'open' check (status in ('open', 'offered', 'accepted', 'dismissed')),
  offer_price       numeric(10,2),
  offer_sent_at     timestamptz,
  offer_expires_at  timestamptz,
  plan_id           uuid references public.plans (id),
  created_at        timestamptz not null default now(),
  resolved_at       timestamptz
);
create unique index if not exists custom_requests_one_open
  on public.custom_requests (tenant_id) where status in ('open', 'offered');
alter table public.custom_requests enable row level security;      -- backend only

revoke execute on function public.plan_period_end(public.plans, timestamptz) from public, anon, authenticated;
grant execute on function public.plan_period_end(public.plans, timestamptz) to service_role;
