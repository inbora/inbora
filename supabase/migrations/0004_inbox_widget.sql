-- ═══════════════════════════════════════════════════════════════════════
-- Inbora — Step 4: inbox and website chat
--
-- Run once in the Supabase SQL editor, after 0003_knowledge.sql.
-- ═══════════════════════════════════════════════════════════════════════

-- When the team took a conversation, and when it last wrote in it. Used to
-- hand a conversation back to the agent after an hour of team silence.
alter table public.threads add column if not exists escalated_at  timestamptz;
alter table public.threads add column if not exists human_last_at timestamptz;
-- Last time an alert went out for this conversation (so alerts aren't spammed).
alter table public.threads add column if not exists notified_at   timestamptz;

-- What the agent asks a website visitor for before passing them to the team.
alter table public.agent_settings
  add column if not exists collect_contact text not null default 'email';
alter table public.agent_settings drop constraint if exists agent_settings_collect_contact_check;
alter table public.agent_settings
  add constraint agent_settings_collect_contact_check
  check (collect_contact in ('email', 'phone', 'either', 'none'));

-- One website chat per business.
create unique index if not exists channels_one_widget
  on public.channels (tenant_id) where type = 'widget';

-- Channels, threads, contacts and messages are now changed only through the
-- Inbora API. Logged-in users can still read their own business's rows.
do $$
declare t text;
begin
  foreach t in array array['channels', 'contacts', 'threads', 'messages']
  loop
    execute format('drop policy if exists %I on public.%I', t || '_member_all', t);
    execute format('drop policy if exists %I on public.%I', t || '_read', t);
    execute format(
      'create policy %I on public.%I for select to authenticated
         using (public.is_tenant_member(tenant_id) or public.is_super_admin())',
      t || '_read', t);
  end loop;
end $$;

-- Inbox list: newest activity first, per business and status.
create index if not exists threads_tenant_status_idx on public.threads (tenant_id, status, last_message_at desc);

-- Which team member wrote a reply (null for the customer and the agent).
alter table public.messages
  add column if not exists author_id uuid references auth.users (id) on delete set null;

-- The inbox list, with filters and search over the contact and the messages.
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
  contact_id uuid, contact_name text, contact_email text, contact_phone text, contact_external_id text
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
         k.id, k.name, k.email, k.phone, k.external_id
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
         or k.name ilike pat.p or k.email ilike pat.p or k.phone ilike pat.p
         or exists (select 1 from public.messages m
                    where m.thread_id = t.id and m.content ilike pat.p))
  order by t.last_message_at desc
  limit least(greatest(coalesce(p_limit, 50), 1), 100);
$$;

-- Badge numbers for the sidebar and the inbox tabs.
create or replace function public.inbox_counts(p_tenant uuid)
returns table (escalated bigint, unread bigint)
language sql stable
set search_path = public
as $$
  select count(*) filter (where status = 'escalated'),
         count(*) filter (where unread)
  from public.threads where tenant_id = p_tenant;
$$;

revoke execute on function public.inbox_threads(uuid, text, text, text, timestamptz, timestamptz, timestamptz, int)
  from public, anon, authenticated;
revoke execute on function public.inbox_counts(uuid) from public, anon, authenticated;
grant execute on function public.inbox_threads(uuid, text, text, text, timestamptz, timestamptz, timestamptz, int)
  to service_role;
grant execute on function public.inbox_counts(uuid) to service_role;
