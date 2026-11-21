-- ═══════════════════════════════════════════════════════════════════════
-- AI tokens per model, so the Super-admin page can show what each business
-- costs in Gemini (each model has its own price). Safe to run again.
-- ═══════════════════════════════════════════════════════════════════════

alter table public.usage_counters
  add column if not exists ai_by_model jsonb not null default '{}';   -- {model: {input, cached, output}}

create or replace function public.add_ai_tokens(p_tenant uuid, p_model text, p_input bigint, p_cached bigint,
                                                p_output bigint)
returns void
language plpgsql security definer set search_path = public
as $$
declare
  cur jsonb;
  m   jsonb;
begin
  cur := public.current_usage(p_tenant);
  if cur ->> 'status' = 'no_plan' then
    return;
  end if;
  select coalesce(ai_by_model -> p_model, '{}') into m from public.usage_counters
   where tenant_id = p_tenant and period_start = (cur ->> 'period_start')::timestamptz for update;
  update public.usage_counters
     set ai_input_tokens  = ai_input_tokens  + greatest(p_input, 0),
         ai_cached_tokens = ai_cached_tokens + greatest(p_cached, 0),
         ai_output_tokens = ai_output_tokens + greatest(p_output, 0),
         ai_by_model = jsonb_set(coalesce(ai_by_model, '{}'), array[coalesce(p_model, 'unknown')], jsonb_build_object(
           'input',  coalesce((m ->> 'input')::bigint, 0)  + greatest(p_input, 0),
           'cached', coalesce((m ->> 'cached')::bigint, 0) + greatest(p_cached, 0),
           'output', coalesce((m ->> 'output')::bigint, 0) + greatest(p_output, 0)))
   where tenant_id = p_tenant and period_start = (cur ->> 'period_start')::timestamptz;
end;
$$;

revoke execute on function public.add_ai_tokens(uuid, text, bigint, bigint, bigint) from public, anon, authenticated;
grant execute on function public.add_ai_tokens(uuid, text, bigint, bigint, bigint) to service_role;
