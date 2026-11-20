-- ═══════════════════════════════════════════════════════════════════════
-- Step 8 — error monitoring and data-deletion requests. Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

-- Errors, grouped: the same error (fingerprint) is one row with a count.
create table if not exists public.error_events (
  id           bigserial primary key,
  fingerprint  text not null unique,
  kind         text not null,                -- api | job | delivery | web | email
  where_       text not null default '',     -- endpoint, job kind, page...
  message      text not null,
  detail       text,                         -- traceback (latest)
  tenant_id    uuid references public.tenants (id) on delete set null,
  count        integer not null default 1,
  first_at     timestamptz not null default now(),
  last_at      timestamptz not null default now(),
  emailed_at   timestamptz
);
create index if not exists error_events_last on public.error_events (last_at desc);
alter table public.error_events enable row level security;      -- backend only

-- Record one error. Returns true when the super-admin should be emailed
-- (first time, or not emailed in the last hour).
create or replace function public.record_error(p_fingerprint text, p_kind text, p_where text, p_message text,
                                               p_detail text, p_tenant uuid)
returns boolean
language plpgsql security definer set search_path = public
as $$
declare
  v_email boolean;
begin
  insert into public.error_events (fingerprint, kind, where_, message, detail, tenant_id)
  values (p_fingerprint, p_kind, left(coalesce(p_where, ''), 300), left(p_message, 1000), left(p_detail, 8000), p_tenant)
  on conflict (fingerprint) do update
     set count = public.error_events.count + 1,
         last_at = now(),
         detail = coalesce(excluded.detail, public.error_events.detail),
         tenant_id = coalesce(excluded.tenant_id, public.error_events.tenant_id);
  update public.error_events
     set emailed_at = now()
   where fingerprint = p_fingerprint
     and (emailed_at is null or emailed_at < now() - interval '1 hour')
  returning true into v_email;
  return coalesce(v_email, false);
end;
$$;
revoke execute on function public.record_error(text, text, text, text, text, uuid) from public, anon, authenticated;
grant execute on function public.record_error(text, text, text, text, text, uuid) to service_role;

-- Someone (a business's customer) asking for their data to be deleted.
create table if not exists public.deletion_requests (
  id            uuid primary key default gen_random_uuid(),
  code          text not null unique,          -- shown to the person, to check the status
  name          text,
  contact       text not null,                 -- email, phone or Instagram username
  business      text,                          -- which business they talked to (optional)
  details       text,
  status        text not null default 'open' check (status in ('open', 'done', 'dismissed')),
  deleted_count integer,
  created_at    timestamptz not null default now(),
  resolved_at   timestamptz
);
alter table public.deletion_requests enable row level security; -- backend only
