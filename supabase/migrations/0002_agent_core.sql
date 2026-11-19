-- ═══════════════════════════════════════════════════════════════════════
-- Inbora — Step 2: agent core
--
-- Run once in the Supabase SQL editor, after 0001_init.sql.
-- Adds what the background worker needs:
--   • threads.reply_epoch — "newest message wins": every customer message bumps
--     it, and a reply generated for an older epoch is thrown away.
--   • claim_jobs()        — workers take queued jobs safely, even several at once.
--   • mark_event_processed() — webhook de-dup that survives restarts.
-- These functions are for the backend only (service role), never the browser.
-- ═══════════════════════════════════════════════════════════════════════

alter table public.threads
  add column if not exists reply_epoch bigint not null default 0;

-- A customer message arrived: invalidate any reply being written for this thread.
create or replace function public.bump_reply_epoch(p_thread uuid)
returns bigint
language sql
as $$
  update public.threads
     set reply_epoch = reply_epoch + 1
   where id = p_thread
  returning reply_epoch;
$$;

-- Take up to p_limit jobs that are due. SKIP LOCKED means two workers never
-- take the same job. Jobs stuck in "running" for 5 minutes (a worker that
-- crashed mid-job) are taken again.
create or replace function public.claim_jobs(p_limit integer default 5)
returns setof public.jobs
language sql
as $$
  update public.jobs j
     set status    = 'running',
         locked_at = now(),
         attempts  = j.attempts + 1
   where j.id in (
           select id
             from public.jobs
            where (status = 'queued' and run_after <= now())
               or (status = 'running' and locked_at < now() - interval '5 minutes')
            order by run_after, id
            limit p_limit
            for update skip locked
         )
  returning j.*;
$$;

-- True the first time an event id is seen, false for a repeat delivery.
create or replace function public.mark_event_processed(p_provider text, p_event_id text)
returns boolean
language plpgsql
as $$
begin
  insert into public.processed_events (provider, event_id)
  values (p_provider, p_event_id);
  return true;
exception when unique_violation then
  return false;
end;
$$;

-- Keep these away from logged-in users and the public API key.
revoke all on function public.bump_reply_epoch(uuid)              from public, anon, authenticated;
revoke all on function public.claim_jobs(integer)                 from public, anon, authenticated;
revoke all on function public.mark_event_processed(text, text)    from public, anon, authenticated;
grant execute on function public.bump_reply_epoch(uuid)           to service_role;
grant execute on function public.claim_jobs(integer)              to service_role;
grant execute on function public.mark_event_processed(text, text) to service_role;

-- Finished jobs are only useful for a few days of debugging.
create index if not exists jobs_finished_idx on public.jobs (created_at) where status in ('done', 'failed');
