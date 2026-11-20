-- ═══════════════════════════════════════════════════════════════════════
-- Step 7 — conversation counting, plan changes, upgrade requests and AI
-- token usage. Safe to run again.
--
-- A conversation = 24 hours from the first AI reply (or AI draft) in a
-- thread. Each new one counts once against the plan's quota. When the quota
-- is used up, the agent stops answering new conversations (the team still
-- gets them) until the next month or an upgrade.
-- ═══════════════════════════════════════════════════════════════════════

alter table public.usage_counters
  add column if not exists alert_80_at       timestamptz,     -- "80% used" sent
  add column if not exists alert_100_at      timestamptz,     -- "limit reached" sent
  add column if not exists ai_input_tokens   bigint not null default 0,
  add column if not exists ai_cached_tokens  bigint not null default 0,
  add column if not exists ai_output_tokens  bigint not null default 0;

-- A business asking for another plan (handled by the super-admin until a
-- payment provider is connected).
create table if not exists public.upgrade_requests (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references public.tenants (id) on delete cascade,
  plan_id       uuid not null references public.plans (id),
  requested_by  uuid references auth.users (id) on delete set null,
  status        text not null default 'open' check (status in ('open', 'done', 'dismissed')),
  created_at    timestamptz not null default now(),
  resolved_at   timestamptz
);
create unique index if not exists upgrade_requests_one_open
  on public.upgrade_requests (tenant_id) where status = 'open';
alter table public.upgrade_requests enable row level security;   -- backend only

-- ── The current billing period (monthly plans move forward by themselves)

create or replace function public.current_usage(p_tenant uuid)
returns jsonb
language plpgsql security definer set search_path = public
as $$
declare
  s public.subscriptions;
  u public.usage_counters;
begin
  select * into s from public.subscriptions
   where tenant_id = p_tenant and status = 'active' for update;
  if not found then
    return jsonb_build_object('status', 'no_plan');
  end if;
  if s.period_end is not null and now() >= s.period_end then
    while now() >= s.period_end loop
      s.period_start := s.period_end;
      s.period_end := s.period_end + interval '1 month';
    end loop;
    update public.subscriptions set period_start = s.period_start, period_end = s.period_end where id = s.id;
  end if;
  insert into public.usage_counters (tenant_id, period_start) values (p_tenant, s.period_start)
  on conflict do nothing;
  select * into u from public.usage_counters where tenant_id = p_tenant and period_start = s.period_start;
  return jsonb_build_object(
    'status', 'ok',
    'period_start', s.period_start,
    'period_end', s.period_end,
    'used', u.conversations_used,
    'quota', coalesce((s.limits ->> 'conversation_quota')::int, 0) + u.bonus_conversations);
end;
$$;

-- ── Count a conversation (called before the agent answers or drafts)
-- Returns status: existing (inside a counted conversation), new (counted now),
-- over (quota used up: don't answer), no_plan. `alert` = 80 or 100 the first
-- time that share of the quota is reached.

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

-- ── AI token usage per business and period (to watch the cost of each plan)

create or replace function public.add_ai_usage(p_tenant uuid, p_input bigint, p_cached bigint, p_output bigint)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  cur jsonb;
begin
  cur := public.current_usage(p_tenant);
  if cur ->> 'status' = 'no_plan' then
    return;
  end if;
  update public.usage_counters
     set ai_input_tokens = ai_input_tokens + greatest(p_input, 0),
         ai_cached_tokens = ai_cached_tokens + greatest(p_cached, 0),
         ai_output_tokens = ai_output_tokens + greatest(p_output, 0)
   where tenant_id = p_tenant and period_start = (cur ->> 'period_start')::timestamptz;
end;
$$;

-- ── Put a business on a plan: the old subscription ends, a new one starts
-- with a snapshot of the plan's limits and a fresh conversation count.

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
  values (p_tenant, p_plan, public.plan_limits(v_plan), v_now,
          case when v_plan.billing_period = 'monthly' then v_now + interval '1 month' else null end,
          p_provider, p_ref)
  returning id into v_sub;
  insert into public.usage_counters (tenant_id, period_start) values (p_tenant, v_now) on conflict do nothing;
  update public.upgrade_requests set status = 'done', resolved_at = v_now
   where tenant_id = p_tenant and status = 'open';
  return v_sub;
end;
$$;

revoke execute on function public.current_usage(uuid) from public, anon, authenticated;
revoke execute on function public.consume_conversation(uuid, uuid) from public, anon, authenticated;
revoke execute on function public.add_ai_usage(uuid, bigint, bigint, bigint) from public, anon, authenticated;
revoke execute on function public.assign_plan(uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.current_usage(uuid) to service_role;
grant execute on function public.consume_conversation(uuid, uuid) to service_role;
grant execute on function public.add_ai_usage(uuid, bigint, bigint, bigint) to service_role;
grant execute on function public.assign_plan(uuid, uuid, text, text) to service_role;
