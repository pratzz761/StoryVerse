-- Phase 3. Additive: published chapters and existing AI contracts are untouched.
begin;
create table public.story_interactions (
  user_id uuid not null references public.profiles(id) on delete cascade,
  story_id uuid not null references public.stories(id) on delete cascade,
  kind text not null check(kind in ('like','bookmark','follow')),
  created_at timestamptz not null default now(),
  primary key(user_id,story_id,kind)
);
create index story_interactions_counts on public.story_interactions(story_id,kind);
alter table public.story_interactions enable row level security;
revoke all on public.story_interactions from anon,authenticated;
grant select,insert,delete on public.story_interactions to authenticated;
create policy interactions_owner on public.story_interactions for all to authenticated
using(user_id=(select auth.uid())) with check(user_id=(select auth.uid()));

-- Aggregates are public; another reader's private action rows are never exposed.
create function public.story_engagement(p_story_ids uuid[]) returns table(
  story_id uuid,like_count bigint,bookmark_count bigint,follow_count bigint,
  "like" boolean,bookmark boolean,follow boolean)
language sql stable security definer set search_path='' as $$
  select s.id,
    count(*) filter(where i.kind='like'),count(*) filter(where i.kind='bookmark'),count(*) filter(where i.kind='follow'),
    coalesce(bool_or(i.kind='like' and i.user_id=auth.uid()),false),
    coalesce(bool_or(i.kind='bookmark' and i.user_id=auth.uid()),false),
    coalesce(bool_or(i.kind='follow' and i.user_id=auth.uid()),false)
  from public.stories s left join public.story_interactions i on i.story_id=s.id
  where s.id=any(p_story_ids[1:60]) group by s.id;
$$;

create function public.set_story_interaction(p_story_id uuid,p_kind text,p_active boolean) returns jsonb
language plpgsql security invoker set search_path='' as $$
begin
  if auth.uid() is null then raise exception 'Sign in required' using errcode='42501'; end if;
  if p_kind is null or p_kind not in ('like','bookmark','follow') or p_active is null then
    raise exception 'Invalid action' using errcode='22023'; end if;
  if not exists(select 1 from public.stories where id=p_story_id) then
    raise exception 'Story not found' using errcode='P0002'; end if;
  if p_active then
    insert into public.story_interactions(user_id,story_id,kind) values(auth.uid(),p_story_id,p_kind) on conflict do nothing;
  else
    delete from public.story_interactions where user_id=auth.uid() and story_id=p_story_id and kind=p_kind;
  end if;
  return (select to_jsonb(e) from public.story_engagement(array[p_story_id]) e);
end;
$$;

create index stories_updated_idx on public.stories(updated_at desc,id);
create function public.discover_stories(p_search text default '',p_genre text default null,p_sort text default 'trending',
  p_page integer default 1,p_page_size integer default 12) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare v_result jsonb;
begin
  if p_page is null or p_page<1 or p_page>100000 or p_page_size is null or p_page_size<1 or p_page_size>60
    or p_sort is null or p_sort not in ('trending','recent') or char_length(coalesce(p_search,''))>100 then
    raise exception 'Invalid discovery parameters' using errcode='22023'; end if;
  with matching as (
    select s.*,
      (select count(*) from public.story_interactions i where i.story_id=s.id and i.kind='like') like_count,
      (select count(*) from public.story_interactions i where i.story_id=s.id and i.kind='bookmark') bookmark_count,
      (select count(*) from public.story_interactions i where i.story_id=s.id and i.kind='follow') follow_count,
      (select count(*) from public.chapters c where c.story_id=s.id) chapter_count
    from public.stories s where (p_genre is null or s.genre=p_genre)
      and strpos(lower(s.title || ' ' || s.description),lower(coalesce(p_search,'')))>0
  ), chosen as (
    select * from matching order by
      case when p_sort='trending' then like_count end desc,
      case when p_sort='trending' then follow_count end desc,
      case when p_sort='trending' then chapter_count end desc,
      updated_at desc,id asc offset (p_page-1)*p_page_size limit p_page_size
  ) select jsonb_build_object('items',coalesce((select jsonb_agg(to_jsonb(chosen) order by
      case when p_sort='trending' then like_count end desc,
      case when p_sort='trending' then follow_count end desc,
      case when p_sort='trending' then chapter_count end desc,updated_at desc,id asc) from chosen),'[]'::jsonb),
      'total',(select count(*) from matching),'page',p_page,'page_size',p_page_size,
      'has_next',(p_page*p_page_size < (select count(*) from matching))) into v_result;
  return v_result;
end;
$$;

alter table public.chapters add constraint chapters_story_id_id_key unique(story_id,id);
create table public.reading_progress (
  user_id uuid not null references public.profiles(id) on delete cascade,
  story_id uuid not null references public.stories(id) on delete cascade,
  chapter_id uuid not null,
  position integer not null check(position>=1),
  completed_position integer not null default 0 check(completed_position>=0),
  layout text not null check(layout in ('webtoon','comic')),
  updated_at timestamptz not null default now(),
  primary key(user_id,story_id),
  foreign key(story_id,chapter_id) references public.chapters(story_id,id)
);
alter table public.reading_progress enable row level security;
revoke all on public.reading_progress from anon,authenticated;
grant select on public.reading_progress to authenticated;
create policy reading_owner on public.reading_progress for select to authenticated using(user_id=(select auth.uid()));

create function public.save_reading_progress(p_story_id uuid,p_chapter_id uuid,p_completed boolean default false,p_layout text default 'webtoon') returns jsonb
language plpgsql security definer set search_path='' as $$
declare v_position integer;
begin
  if auth.uid() is null then raise exception 'Sign in required' using errcode='42501'; end if;
  if p_layout is null or p_layout not in ('webtoon','comic') or p_completed is null then
    raise exception 'Invalid reading state' using errcode='22023'; end if;
  select position into v_position from public.chapters where id=p_chapter_id and story_id=p_story_id;
  if v_position is null then raise exception 'Chapter/story mismatch' using errcode='22023'; end if;
  insert into public.reading_progress as r(user_id,story_id,chapter_id,position,completed_position,layout)
  values(auth.uid(),p_story_id,p_chapter_id,v_position,case when p_completed then v_position else 0 end,p_layout)
  on conflict(user_id,story_id) do update set chapter_id=excluded.chapter_id,position=excluded.position,
    completed_position=greatest(r.completed_position,excluded.completed_position),layout=excluded.layout,updated_at=now()
  where r.chapter_id<>excluded.chapter_id or r.layout<>excluded.layout or r.completed_position<excluded.completed_position;
  return (select to_jsonb(r) from public.reading_progress r where r.user_id=auth.uid() and r.story_id=p_story_id);
end;
$$;

revoke all on function public.story_engagement(uuid[]),public.discover_stories(text,text,text,integer,integer),
  public.set_story_interaction(uuid,text,boolean),public.save_reading_progress(uuid,uuid,boolean,text) from public,anon,authenticated;
grant execute on function public.story_engagement(uuid[]),public.discover_stories(text,text,text,integer,integer) to anon,authenticated;
grant execute on function public.set_story_interaction(uuid,text,boolean),public.save_reading_progress(uuid,uuid,boolean,text) to authenticated;

-- An empty optional visual description is unknown, not an immutable visual fact.
-- Permit filling it once while retaining the original containment guard for all
-- established descriptions, traits, relationships, events and chapter history.
create or replace function public.chapter_memory() returns trigger
language plpgsql security definer set search_path='' as $$
declare v_old jsonb; v_required jsonb; v_data jsonb; v_ai jsonb; v_line text;
begin
  insert into public.story_bibles(story_id) values(new.story_id) on conflict do nothing;
  select data into v_old from public.story_bibles where story_id=new.story_id for update;
  v_data := v_old;
  if new.source='ai_generated' then
    select ai_data into v_ai from public.drafts where id=new.draft_id;
    v_data := v_ai->'bible_after';
    v_required := jsonb_set(v_old,'{characters}',coalesce((select jsonb_agg(
      case when coalesce(c->>'visual_description','')='' then c-'visual_description' else c end)
      from jsonb_array_elements(coalesce(v_old->'characters','[]'::jsonb)) c),'[]'::jsonb));
    if v_data is null or not (v_data @> v_required) or octet_length(v_data::text)>16000 then
      raise exception 'Established canon cannot be replaced' using errcode='22023';
    end if;
    new.summary := (v_ai->'memory'->'summary') || '{"source":"ai"}'::jsonb;
    new.comic_prompts := coalesce(v_ai->'panels','[]'::jsonb);
    new.ai_metadata := jsonb_build_object('model',v_ai->>'model','is_test_fixture',coalesce((v_ai->>'is_test_fixture')::boolean,false));
  else
    new.summary := jsonb_build_object('synopsis',left(new.narrative,600),'events','[]'::jsonb,'characters','[]'::jsonb,'unresolved_plotlines','[]'::jsonb,'source','extractive');
  end if;
  v_line := left('Chapter ' || new.position || ': ' || new.title,500);
  v_data := jsonb_set(v_data,'{timeline}',coalesce(v_data->'timeline','[]'::jsonb) || jsonb_build_array(v_line));
  update public.story_bibles set data=v_data,version=new.position,updated_at=now() where story_id=new.story_id;
  return new;
end;
$$;
commit;
