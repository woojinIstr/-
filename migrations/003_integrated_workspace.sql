-- Apply AFTER 001 and 002. Existing rows are preserved; import occurs on first v3 login.
begin;
create table if not exists public.nextmeal_workspaces (
  user_id uuid primary key references auth.users(id) on delete cascade,
  revision bigint not null default 0 check (revision >= 0),
  document jsonb not null,
  updated_at timestamptz not null default now(),
  constraint nextmeal_workspace_shape check (
    jsonb_typeof(document)='object' and document->>'schema'='3'
    and jsonb_typeof(document->'ingredients')='array'
    and jsonb_typeof(document->'recipes')='array'
    and jsonb_typeof(document->'inventory')='array'
    and jsonb_typeof(document->'meals')='array'
  )
);
alter table public.nextmeal_workspaces enable row level security;
drop policy if exists nextmeal_workspace_select on public.nextmeal_workspaces;
create policy nextmeal_workspace_select on public.nextmeal_workspaces for select to authenticated using (auth.uid()=user_id);
revoke all on public.nextmeal_workspaces from anon, authenticated;
grant select on public.nextmeal_workspaces to authenticated;

create or replace function public.nextmeal_workspace_put(p_expected_revision bigint, p_document jsonb)
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare owner_id uuid := auth.uid(); affected integer;
begin
  if owner_id is null then raise exception 'Authentication required' using errcode='42501'; end if;
  if p_expected_revision < -1 or p_document is null or octet_length(p_document::text)>8388608 then
    raise exception 'Invalid workspace payload' using errcode='22023';
  end if;
  if p_expected_revision=-1 then
    insert into public.nextmeal_workspaces(user_id,revision,document) values(owner_id,0,p_document) on conflict(user_id) do nothing;
  else
    update public.nextmeal_workspaces set document=p_document,revision=revision+1,updated_at=now()
      where user_id=owner_id and revision=p_expected_revision;
  end if;
  get diagnostics affected = row_count;
  return jsonb_build_object('saved',affected=1);
end; $$;
revoke all on function public.nextmeal_workspace_put(bigint,jsonb) from public,anon;
grant execute on function public.nextmeal_workspace_put(bigint,jsonb) to authenticated;
commit;
