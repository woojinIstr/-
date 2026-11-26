-- Apply once AFTER 001_inventory.sql. Existing inventory is retained.
begin;
create table public.recipes (
 recipe_id uuid primary key default gen_random_uuid(),
 recipe_name text not null,
 base_servings numeric not null check(base_servings>0 and base_servings<=12),
 cooking_time_minutes integer not null check(cooking_time_minutes>0),
 description text not null default ''
);
create table public.recipe_ingredients (
 recipe_id uuid not null references public.recipes(recipe_id),
 ingredient_id uuid not null,
 required_quantity numeric not null check(required_quantity>0 and required_quantity<=1000000000),
 unit text not null,
 primary key(recipe_id,ingredient_id),
 foreign key(ingredient_id,unit) references public.ingredients(ingredient_id,unit)
);
create table public.meals (
 meal_id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 meal_date date not null,
 meal_slot text not null check(meal_slot in ('breakfast','lunch','dinner')),
 recipe_id uuid not null references public.recipes(recipe_id),
 servings numeric not null check(servings>0 and servings<=12),
 meal_status text not null default 'planned' check(meal_status in ('planned','eating_out','cancelled')),
 version integer not null default 0 check(version>=0),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
create index meals_owner_date_idx on public.meals(user_id,meal_date);
alter table public.recipes enable row level security;
alter table public.recipe_ingredients enable row level security;
alter table public.meals enable row level security;
revoke all on public.recipes,public.recipe_ingredients,public.meals from anon,authenticated;
grant select on public.recipes,public.recipe_ingredients to authenticated;
grant select,insert,update on public.meals to authenticated;
create policy recipe_read on public.recipes for select to authenticated using(true);
create policy recipe_ingredient_read on public.recipe_ingredients for select to authenticated using(true);
create policy meal_read on public.meals for select to authenticated using((select auth.uid())=user_id);
create policy meal_insert on public.meals for insert to authenticated with check((select auth.uid())=user_id and meal_status='planned' and version=0);
create policy meal_update on public.meals for update to authenticated using((select auth.uid())=user_id and meal_status='planned') with check((select auth.uid())=user_id);
create function public.meal_guard() returns trigger language plpgsql set search_path='' as $$
begin
 if TG_OP='INSERT' then
  if new.meal_status<>'planned' or new.version<>0 then raise exception 'New meal must be planned with version zero'; end if;
  new.created_at=now();
 else
  if new.meal_id<>old.meal_id or new.user_id<>old.user_id then raise exception 'Meal identity is immutable'; end if;
  if old.meal_status<>'planned' then raise exception 'Only planned meals can change'; end if;
  if new.version<>old.version+1 then raise exception 'Meal version must increase by one'; end if;
  new.created_at=old.created_at;
 end if;
 new.updated_at=now();
 return new;
end;
$$;
create trigger meal_guard before insert or update on public.meals for each row execute function public.meal_guard();

insert into public.ingredients(ingredient_id,ingredient_name,unit) values
('10000000-0000-4000-8000-000000000004','밥','g'),
('10000000-0000-4000-8000-000000000005','우유','ml'),
('10000000-0000-4000-8000-000000000006','파스타면','g'),
('10000000-0000-4000-8000-000000000007','양파','g'),
('10000000-0000-4000-8000-000000000008','토마토 소스','g');

insert into public.recipes(recipe_id,recipe_name,base_servings,cooking_time_minutes,description) values
('20000000-0000-4000-8000-000000000001','닭가슴살 시금치 리소토',1,15,'닭가슴살과 시금치를 활용하는 간단한 한 끼'),
('20000000-0000-4000-8000-000000000002','닭가슴살 볶음밥',1,20,'닭가슴살과 밥을 활용하는 볶음밥'),
('20000000-0000-4000-8000-000000000003','토마토 파스타',1,25,'파스타면을 활용하는 기본 메뉴'),
('20000000-0000-4000-8000-000000000004','우유 리소토',1,15,'밥과 우유를 활용하는 부드러운 리소토');

insert into public.recipe_ingredients(recipe_id,ingredient_id,required_quantity,unit) values
('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000001',150,'g'),
('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000002',100,'g'),
('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000004',210,'g'),
('20000000-0000-4000-8000-000000000001','10000000-0000-4000-8000-000000000005',150,'ml'),
('20000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000001',150,'g'),
('20000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000004',210,'g'),
('20000000-0000-4000-8000-000000000002','10000000-0000-4000-8000-000000000007',100,'g'),
('20000000-0000-4000-8000-000000000003','10000000-0000-4000-8000-000000000006',100,'g'),
('20000000-0000-4000-8000-000000000003','10000000-0000-4000-8000-000000000008',150,'g'),
('20000000-0000-4000-8000-000000000003','10000000-0000-4000-8000-000000000007',100,'g'),
('20000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000004',210,'g'),
('20000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000005',200,'ml'),
('20000000-0000-4000-8000-000000000004','10000000-0000-4000-8000-000000000007',50,'g');

commit;
