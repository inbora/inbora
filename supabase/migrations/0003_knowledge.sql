-- ═══════════════════════════════════════════════════════════════════════
-- Inbora — Step 3: knowledge articles and agent settings
--
-- Run once in the Supabase SQL editor, after 0002_agent_core.sql.
-- Articles and agent settings are now changed only through the Inbora API,
-- which checks the plan's knowledge size limit. Logged-in users can still
-- read their own business's rows directly.
-- ═══════════════════════════════════════════════════════════════════════

drop policy if exists kb_articles_member_all on public.kb_articles;
drop policy if exists kb_articles_read on public.kb_articles;
create policy kb_articles_read on public.kb_articles
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());

drop policy if exists agent_settings_member_all on public.agent_settings;
drop policy if exists agent_settings_read on public.agent_settings;
create policy agent_settings_read on public.agent_settings
  for select to authenticated
  using (public.is_tenant_member(tenant_id) or public.is_super_admin());

-- Tone is one of a fixed set the panel offers.
update public.agent_settings set tone = 'friendly'
 where tone not in ('friendly', 'professional', 'casual', 'formal');
alter table public.agent_settings drop constraint if exists agent_settings_tone_check;
alter table public.agent_settings
  add constraint agent_settings_tone_check check (tone in ('friendly', 'professional', 'casual', 'formal'));
