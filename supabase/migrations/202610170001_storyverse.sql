-- Phase 1. Apply once to a Supabase project, using `supabase db push` or SQL Editor.
begin;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null check (char_length(btrim(display_name)) between 1 and 50),
  bio text not null default '' check (char_length(bio) <= 300),
  avatar_color text not null default 'purple' check (avatar_color in ('purple','green','orange')),
  created_at timestamptz not null default now()
);

create table public.uploads (
  id uuid primary key,
  owner_id uuid not null references public.profiles(id),
  filename text not null check (char_length(filename) between 1 and 150),
  mime_type text not null check (mime_type in ('image/jpeg','image/png','image/webp','image/gif','audio/mpeg','audio/wav','audio/ogg','audio/mp4','audio/webm','video/mp4','video/webm')),
  size_bytes bigint not null check (size_bytes between 1 and 20971520),
  storage_path text not null unique,
  is_public boolean not null default false,
  created_at timestamptz not null default now(),
  check (storage_path = owner_id::text || '/' || id::text)
);

create table public.stories (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id),
  title text not null check (char_length(btrim(title)) between 1 and 100),
  genre text not null check (genre in ('Fantasy','Sci-Fi','Mystery','Adventure','Romance','Horror','Slice of Life')),
  description text not null default '',
  cover_art text not null default 'forest' check (cover_art in ('forest','space','city','ocean','moon','desert')),
  cover_upload_id uuid references public.uploads(id),
  version integer not null default 1 check (version >= 1),
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.contributions (
  id uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.stories(id),
  author_id uuid not null references public.profiles(id),
  text text not null check (char_length(text) <= 12000),
  direction text not null check (direction in ('Keep it going','Add a twist','Build the world','Meet someone new')),
  upload_ids uuid[] not null default '{}',
  expected_version integer not null check (expected_version >= 1),
  created_at timestamptz not null default now(),
  check (cardinality(upload_ids) <= 6),
  check (char_length(btrim(text)) > 0 or cardinality(upload_ids) > 0)
);

create table public.drafts (
  id uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.stories(id),
  owner_id uuid not null references public.profiles(id),
  contribution_id uuid not null unique references public.contributions(id),
  title text not null check (char_length(btrim(title)) between 1 and 100),
  narrative text not null check (char_length(narrative) <= 12000),
  base_version integer not null check (base_version >= 1),
  upload_ids uuid[] not null default '{}',
  status text not null default 'draft' check (status in ('draft','published')),
  source text not null default 'demo_preview' check (source = 'demo_preview'),
  created_at timestamptz not null default now()
);

create table public.chapters (
  id uuid primary key default gen_random_uuid(),
  story_id uuid not null references public.stories(id),
  author_id uuid not null references public.profiles(id),
  draft_id uuid unique references public.drafts(id),
  position integer not null check (position >= 1),
  title text not null check (char_length(btrim(title)) between 1 and 100),
  narrative text not null check (char_length(btrim(narrative)) between 1 and 12000),
  upload_ids uuid[] not null default '{}',
  source text not null check (source in ('manual','sample','demo_preview')),
  created_at timestamptz not null default now(),
  unique(story_id,position)
);

create table public.panels (
  id uuid primary key default gen_random_uuid(),
  chapter_id uuid not null references public.chapters(id),
  upload_id uuid not null references public.uploads(id),
  position integer not null check (position >= 1),
  caption text not null default '',
  unique(chapter_id,position)
);

create index chapters_author_idx on public.chapters(author_id);
create index stories_owner_idx on public.stories(owner_id);
create index stories_recent_idx on public.stories(created_at desc);
create index contributions_author_idx on public.contributions(author_id);
create index drafts_owner_idx on public.drafts(owner_id,status);
create index uploads_owner_idx on public.uploads(owner_id);

-- Provision profiles without exposing email addresses in the public profile table.
create function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles(id,display_name)
  values (new.id, left(coalesce(nullif(btrim(new.raw_user_meta_data->>'display_name'),''),'New storyteller'),50));
  return new;
end;
$$;
create trigger on_auth_user_created after insert on auth.users
for each row execute function public.handle_new_user();
insert into public.profiles(id,display_name)
select id, left(coalesce(nullif(btrim(raw_user_meta_data->>'display_name'),''),'New storyteller'),50)
from auth.users on conflict (id) do nothing;

alter table public.profiles enable row level security;
alter table public.stories enable row level security;
alter table public.chapters enable row level security;
alter table public.panels enable row level security;
alter table public.contributions enable row level security;
alter table public.drafts enable row level security;
alter table public.uploads enable row level security;

-- Revoke project defaults. Chapter/story writes are possible only through the RPCs below.
revoke all on public.profiles,public.stories,public.chapters,public.panels,public.contributions,public.drafts,public.uploads from anon,authenticated;
grant select on public.profiles,public.stories,public.chapters,public.panels to anon,authenticated;
grant select on public.uploads to anon,authenticated;
grant select on public.contributions,public.drafts to authenticated;
grant update(display_name,bio) on public.profiles to authenticated;
grant update(title,narrative) on public.drafts to authenticated;
grant insert(id,owner_id,filename,mime_type,size_bytes,storage_path) on public.uploads to authenticated;

create policy profiles_public_read on public.profiles for select using (true);
create policy profiles_owner_update on public.profiles for update to authenticated
using (id = (select auth.uid())) with check (id = (select auth.uid()));
create policy stories_public_read on public.stories for select using (true);
create policy chapters_public_read on public.chapters for select using (true);
create policy panels_public_read on public.panels for select using (true);
create policy contributions_private on public.contributions for select to authenticated using (author_id = (select auth.uid()));
create policy drafts_private on public.drafts for select to authenticated using (owner_id = (select auth.uid()));
create policy drafts_owner_update on public.drafts for update to authenticated
using (owner_id = (select auth.uid()) and status = 'draft')
with check (owner_id = (select auth.uid()) and status = 'draft');
create policy uploads_read on public.uploads for select using (is_public or owner_id = (select auth.uid()));
create policy uploads_insert on public.uploads for insert to authenticated
with check (owner_id = (select auth.uid()) and not is_public);

-- Private helper. Do not grant execution to clients.
create function public.check_owned_uploads(p_ids uuid[], p_user uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  if p_ids is null or cardinality(p_ids) > 6
    or cardinality(p_ids) <> (select count(distinct x) from unnest(p_ids) x)
    or exists(select 1 from unnest(p_ids) x where not exists(select 1 from public.uploads u where u.id=x and u.owner_id=p_user))
  then raise exception 'Invalid attachments' using errcode='22023'; end if;
end;
$$;

create function public.create_story(p_title text,p_genre text,p_narrative text,p_upload_ids uuid[] default '{}')
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid(); v_id uuid; v_chapter uuid; v_cover uuid;
begin
  if v_user is null then raise exception 'Sign in required' using errcode='42501'; end if;
  perform public.check_owned_uploads(p_upload_ids,v_user);
  select id into v_cover from public.uploads where id=any(p_upload_ids) and mime_type like 'image/%' order by array_position(p_upload_ids,id) limit 1;
  insert into public.stories(owner_id,title,genre,description,cover_upload_id)
  values(v_user,btrim(p_title),p_genre,left(p_narrative,180),v_cover) returning id into v_id;
  insert into public.chapters(story_id,author_id,position,title,narrative,source,upload_ids)
  values(v_id,v_user,1,'The beginning',btrim(p_narrative),'manual',p_upload_ids) returning id into v_chapter;
  insert into public.panels(chapter_id,upload_id,position,caption)
  select v_chapter,u.id,row_number() over(order by array_position(p_upload_ids,u.id)),u.filename
  from public.uploads u where u.id=any(p_upload_ids) and u.mime_type like 'image/%';
  update public.uploads set is_public=true where id=any(p_upload_ids);
  return v_id;
end;
$$;

-- Phase 1 preview copies the contribution verbatim. It is never AI output.
create function public.create_contribution_preview(p_story_id uuid,p_text text,p_direction text,p_expected_version integer,p_upload_ids uuid[] default '{}')
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_user uuid := auth.uid(); v_version integer; v_contribution uuid; v_draft uuid;
begin
  if v_user is null then raise exception 'Sign in required' using errcode='42501'; end if;
  select version into v_version from public.stories where id=p_story_id for share;
  if not found then raise exception 'Story not found' using errcode='P0002'; end if;
  if v_version is distinct from p_expected_version then raise exception 'Story changed' using errcode='40001'; end if;
  perform public.check_owned_uploads(p_upload_ids,v_user);
  insert into public.contributions(story_id,author_id,text,direction,expected_version,upload_ids)
  values(p_story_id,v_user,p_text,p_direction,v_version,p_upload_ids) returning id into v_contribution;
  insert into public.drafts(story_id,owner_id,contribution_id,title,narrative,base_version,upload_ids)
  values(p_story_id,v_user,v_contribution,'Chapter ' || (v_version+1),btrim(p_text),v_version,p_upload_ids) returning id into v_draft;
  return v_draft;
end;
$$;

create function public.reset_demo_preview(p_draft_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare v_draft public.drafts;
begin
  select * into v_draft from public.drafts where id=p_draft_id and owner_id=auth.uid() for update;
  if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
  if v_draft.status <> 'draft' then raise exception 'Already published' using errcode='40001'; end if;
  update public.drafts set title='Chapter ' || (base_version+1),
    narrative=(select btrim(text) from public.contributions where id=v_draft.contribution_id)
  where id=p_draft_id;
end;
$$;

-- All publication effects commit together. Row locks serialize contributors to one story.
-- Expected version and draft base version must both equal the locked story version.
create function public.publish_chapter(p_draft_id uuid,p_expected_version integer,p_approved boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_draft public.drafts; v_story public.stories; v_chapter uuid;
begin
  if auth.uid() is null or p_approved is distinct from true then
    raise exception 'Explicit approval required' using errcode='42501';
  end if;
  select * into v_draft from public.drafts where id=p_draft_id and owner_id=auth.uid() for update;
  if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
  select * into v_story from public.stories where id=v_draft.story_id for update;
  if v_draft.status <> 'draft' or v_story.version is distinct from p_expected_version or v_draft.base_version is distinct from p_expected_version then
    raise exception 'Publication conflict' using errcode='40001';
  end if;
  if char_length(btrim(v_draft.narrative)) = 0 then raise exception 'Narrative required' using errcode='22023'; end if;
  perform public.check_owned_uploads(v_draft.upload_ids,auth.uid());
  insert into public.chapters(story_id,author_id,draft_id,position,title,narrative,upload_ids,source)
  values(v_story.id,auth.uid(),v_draft.id,v_story.version+1,v_draft.title,v_draft.narrative,v_draft.upload_ids,'demo_preview')
  returning id into v_chapter;
  insert into public.panels(chapter_id,upload_id,position,caption)
  select v_chapter,u.id,row_number() over(order by array_position(v_draft.upload_ids,u.id)),u.filename
  from public.uploads u where u.id=any(v_draft.upload_ids) and u.mime_type like 'image/%';
  update public.stories set version=version+1,updated_at=now() where id=v_story.id;
  update public.drafts set status='published' where id=v_draft.id;
  update public.uploads set is_public=true where id=any(v_draft.upload_ids);
  return jsonb_build_object('story_id',v_story.id,'chapter_id',v_chapter,'version',v_story.version+1);
end;
$$;

-- Filter and rank before limiting, so search covers the full catalog.
create function public.story_feed(p_search text default '',p_genre text default null,p_sort text default 'trending')
returns setof public.stories language sql stable security invoker set search_path = '' as $$
  select s.* from public.stories s
  where (p_genre is null or s.genre=p_genre)
    and strpos(lower(s.title || ' ' || s.description),lower(p_search)) > 0
  order by
    case when p_sort='trending' then (select count(distinct c.author_id) from public.chapters c where c.story_id=s.id) end desc,
    case when p_sort='trending' then s.version end desc,
    case when p_sort='trending' then s.updated_at else s.created_at end desc
  limit 60;
$$;

revoke all on function public.handle_new_user() from public,anon,authenticated;
revoke all on function public.check_owned_uploads(uuid[],uuid) from public,anon,authenticated;
revoke all on function public.create_story(text,text,text,uuid[]) from public,anon,authenticated;
revoke all on function public.create_contribution_preview(uuid,text,text,integer,uuid[]) from public,anon,authenticated;
revoke all on function public.reset_demo_preview(uuid) from public,anon,authenticated;
revoke all on function public.publish_chapter(uuid,integer,boolean) from public,anon,authenticated;
grant execute on function public.create_story(text,text,text,uuid[]) to authenticated;
grant execute on function public.create_contribution_preview(uuid,text,text,integer,uuid[]) to authenticated;
grant execute on function public.reset_demo_preview(uuid) to authenticated;
grant execute on function public.publish_chapter(uuid,integer,boolean) to authenticated;
revoke all on function public.story_feed(text,text,text) from public,anon,authenticated;
grant execute on function public.story_feed(text,text,text) to anon,authenticated;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('story-media','story-media',false,20971520,array['image/jpeg','image/png','image/webp','image/gif','audio/mpeg','audio/wav','audio/ogg','audio/mp4','audio/webm','video/mp4','video/webm']);
create policy story_media_insert on storage.objects for insert to authenticated
with check(bucket_id='story-media' and (storage.foldername(name))[1]=(select auth.uid())::text
  and cardinality(storage.foldername(name))=1);
create policy story_media_read on storage.objects for select
using(bucket_id='story-media' and ((storage.foldername(name))[1]=(select auth.uid())::text
  or exists(select 1 from public.uploads u where u.storage_path=name and u.is_public)));
-- Only unpublished objects can be removed, for compensation after a failed metadata insert.
create policy story_media_delete on storage.objects for delete to authenticated
using(bucket_id='story-media' and (storage.foldername(name))[1]=(select auth.uid())::text
  and not exists(select 1 from public.uploads u where u.storage_path=name));

commit;
