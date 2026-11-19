-- ═══════════════════════════════════════════════════════════════════════
-- Step 5 — WhatsApp and Instagram (through Zernio). Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

-- One WhatsApp number and one Instagram account per business.
create unique index if not exists channels_one_whatsapp
  on public.channels (tenant_id) where type = 'whatsapp' and status <> 'disconnected';
create unique index if not exists channels_one_instagram
  on public.channels (tenant_id) where type = 'instagram' and status <> 'disconnected';

-- A reply that WhatsApp or Instagram refused (for example after the 24-hour
-- window closed) keeps the reason, so the inbox can show it.
alter table public.messages add column if not exists delivery_error text;

-- Images sent and received in conversations. Public bucket: files are only
-- reachable by their long random path.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('inbora-media', 'inbora-media', true, 10485760,
        array['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
on conflict (id) do nothing;
