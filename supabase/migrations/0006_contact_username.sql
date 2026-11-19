-- ═══════════════════════════════════════════════════════════════════════
-- The customer's Instagram @username, kept apart from their name, so the
-- inbox can show both. Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

alter table public.contacts add column if not exists username text;

-- The inbox list now also returns (and searches) the @username.
drop function if exists public.inbox_threads(uuid, text, text, text, timestamptz, timestamptz, timestamptz, int);

create or replace function public.inbox_threads(
  p_tenant  uuid,
  p_filter  text        default 'all',     -- all | escalated | unread | bot
  p_channel text        default null,      -- widget | whatsapp | instagram | email
  p_q       text        default null,      -- search text
  p_from    timestamptz default null,      -- last activity on or after
  p_to      timestamptz default null,      -- last activity before
  p_before  timestamptz default null,      -- paging: older than this
  p_limit   int         default 50
)
returns table (
  id uuid, status text, escalation_reason text, unread boolean,
  last_message_at timestamptz, last_message_preview text, escalated_at timestamptz,
  channel_id uuid, channel_type text,
  contact_id uuid, contact_name text, contact_email text, contact_phone text, contact_external_id text,
  contact_username text
)
language sql stable
set search_path = public
as $$
  with pat as (
    select case when coalesce(btrim(p_q), '') = '' then null
           else '%' || replace(replace(replace(btrim(p_q), '\', '\\'), '%', '\%'), '_', '\_') || '%'
           end as p
  )
  select t.id, t.status, t.escalation_reason, t.unread,
         t.last_message_at, t.last_message_preview, t.escalated_at,
         c.id, c.type,
         k.id, k.name, k.email, k.phone, k.external_id, k.username
  from public.threads t
  join public.channels c on c.id = t.channel_id
  join public.contacts k on k.id = t.contact_id
  cross join pat
  where t.tenant_id = p_tenant
    and case p_filter
          when 'escalated' then t.status = 'escalated'
          when 'unread'    then t.unread
          when 'bot'       then t.status = 'bot'
          else true
        end
    and (p_channel is null or c.type = p_channel)
    and (p_from   is null or t.last_message_at >= p_from)
    and (p_to     is null or t.last_message_at <  p_to)
    and (p_before is null or t.last_message_at <  p_before)
    and (pat.p is null
         or k.name ilike pat.p or k.email ilike pat.p or k.phone ilike pat.p or k.username ilike pat.p
         or exists (select 1 from public.messages m
                    where m.thread_id = t.id and m.content ilike pat.p))
  order by t.last_message_at desc
  limit least(greatest(coalesce(p_limit, 50), 1), 100);
$$;

revoke execute on function public.inbox_threads(uuid, text, text, text, timestamptz, timestamptz, timestamptz, int) from public, anon, authenticated;
grant execute on function public.inbox_threads(uuid, text, text, text, timestamptz, timestamptz, timestamptz, int) to service_role;
