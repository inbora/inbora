-- ═══════════════════════════════════════════════════════════════════════
-- Knowledge from the business's website. Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

-- The address the business entered (filled in next time).
alter table public.tenants add column if not exists website text;

-- One import: the pages read, then the suggested articles waiting for review.
create table if not exists public.site_imports (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null references public.tenants (id) on delete cascade,
  url          text not null,
  language     text not null default 'en',
  status       text not null default 'queued'
               check (status in ('queued', 'reading', 'writing', 'ready', 'failed', 'done', 'dismissed')),
  pages_done   integer not null default 0,    -- pages tried so far
  pages_total  integer not null default 0,    -- pages planned (grows while links are found)
  pages_read   integer not null default 0,    -- pages with useful text
  suggestions  jsonb not null default '[]',   -- [{title, body, source}]
  error        text,                          -- unreachable | empty | failed
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists site_imports_tenant on public.site_imports (tenant_id, created_at desc);
alter table public.site_imports enable row level security;      -- backend only
