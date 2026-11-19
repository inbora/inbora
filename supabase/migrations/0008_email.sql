-- ═══════════════════════════════════════════════════════════════════════
-- Step 6 — Email (through Zernio). Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

-- One mailbox per business.
create unique index if not exists channels_one_email
  on public.channels (tenant_id) where type = 'email' and status <> 'disconnected';

-- The subject line of an email (empty for chat messages).
alter table public.messages add column if not exists subject text;
