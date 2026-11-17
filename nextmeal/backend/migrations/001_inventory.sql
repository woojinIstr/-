-- Apply once in a dedicated Supabase project's SQL Editor. No destructive DDL.
begin;
create table public.ingredients (
 ingredient_id uuid primary key default gen_random_uuid(),
 ingredient_name text not null check(length(trim(ingredient_name)) > 0),
 unit text not null check(unit in ('g','ml','count')),
 unique(ingredient_id,unit)
);
create table public.inventory (
 inventory_id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 ingredient_id uuid not null,
 quantity numeric not null check(quantity >= 0 and quantity <= 1000000000),
 unit text not null,
 storage_location text not null check(storage_location in ('fridge','freezer','pantry')),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 foreign key(ingredient_id,unit) references public.ingredients(ingredient_id,unit)
);
create index inventory_owner_idx on public.inventory(user_id);
alter table public.ingredients enable row level security;
alter table public.inventory enable row level security;
revoke all on public.ingredients, public.inventory from anon;
revoke all on public.ingredients, public.inventory from authenticated;
grant select on public.ingredients to authenticated;
grant select, insert, update, delete on public.inventory to authenticated;
create policy ingredient_read on public.ingredients for select to authenticated using(true);
create policy inventory_owner on public.inventory for all to authenticated
 using((select auth.uid()) = user_id) with check((select auth.uid()) = user_id);
create function public.inventory_touch() returns trigger language plpgsql set search_path = '' as $$
begin
 new.updated_at = now();
 new.created_at = old.created_at;
 if new.user_id <> old.user_id or new.inventory_id <> old.inventory_id then
  raise exception 'Inventory owner and identity are immutable';
 end if;
 return new;
end;
$$;
create trigger inventory_touch before update on public.inventory for each row execute function public.inventory_touch();
insert into public.ingredients(ingredient_id,ingredient_name,unit) values
 ('10000000-0000-4000-8000-000000000001','닭가슴살','g'),
 ('10000000-0000-4000-8000-000000000002','시금치','g'),
 ('10000000-0000-4000-8000-000000000003','달걀','count');
commit;
