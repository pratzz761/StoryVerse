-- Phase 4: persistent outbound GPU queue, abuse bounds, reports and moderation.
-- Additive; no existing story/chapter/draft is deleted or rewritten.
begin;

-- Remote callbacks use a trusted backend identity, not a stored user JWT.
-- Do not depend on a project's default table grants for private upload metadata.
grant select,insert on public.uploads to service_role;

alter table public.stories add column is_hidden boolean not null default false;
create table public.moderators(user_id uuid primary key references public.profiles(id));
create table public.content_reports(
  id uuid primary key default gen_random_uuid(), story_id uuid not null references public.stories(id),
  reporter_id uuid not null references public.profiles(id),
  reason text not null check(reason in ('spam','harassment','sexual_content','violence','privacy','copyright','other')),
  details text not null default '' check(char_length(details)<=1000),
  status text not null default 'open' check(status in ('open','reviewed')),
  created_at timestamptz not null default now(), unique(story_id,reporter_id)
);
create table public.moderation_audit(
  id uuid primary key default gen_random_uuid(), story_id uuid not null references public.stories(id),
  moderator_id uuid not null references public.profiles(id), hidden boolean not null,
  reason text not null check(char_length(reason) between 5 and 500), created_at timestamptz not null default now()
);
alter table public.moderators enable row level security;
alter table public.content_reports enable row level security;
alter table public.moderation_audit enable row level security;
revoke all on public.moderators,public.content_reports,public.moderation_audit from public,anon,authenticated;

create function public.story_visible(p_story uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.stories where id=p_story and not is_hidden);
$$;
create function public.upload_visible(p_upload uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.stories where cover_upload_id=p_upload and not is_hidden)
 or exists(select 1 from public.chapters c join public.stories s on s.id=c.story_id
   where not s.is_hidden and (p_upload=any(c.upload_ids) or exists(select 1 from public.panels p where p.chapter_id=c.id and p.upload_id=p_upload)));
$$;
revoke all on function public.story_visible(uuid),public.upload_visible(uuid) from public;
grant execute on function public.story_visible(uuid),public.upload_visible(uuid) to anon,authenticated;
alter policy stories_public_read on public.stories using(not is_hidden);
alter policy chapters_public_read on public.chapters using(public.story_visible(story_id));
alter policy panels_public_read on public.panels using(exists(select 1 from public.chapters c where c.id=chapter_id));
alter policy story_bible_public on public.story_bibles using(public.story_visible(story_id));
alter policy uploads_read on public.uploads using(owner_id=(select auth.uid()) or (is_public and public.upload_visible(id)));

create function public.report_story(p_story uuid,p_reason text,p_details text default '') returns jsonb
language plpgsql security definer set search_path='' as $$
declare v_id uuid;
begin
 if auth.uid() is null then raise exception 'Sign in required' using errcode='42501'; end if;
 if not public.story_visible(p_story) then raise exception 'Story not found' using errcode='P0002'; end if;
 if (select count(*) from public.content_reports where reporter_id=auth.uid() and created_at>now()-interval '1 day')>=10
   and not exists(select 1 from public.content_reports where story_id=p_story and reporter_id=auth.uid()) then
   raise exception 'WRITE_QUOTA' using errcode='P0001'; end if;
 insert into public.content_reports(story_id,reporter_id,reason,details) values(p_story,auth.uid(),p_reason,p_details)
 on conflict(story_id,reporter_id) do update set story_id=excluded.story_id returning id into v_id;
 return jsonb_build_object('id',v_id,'status','received');
end;
$$;
create function public.moderation_reports() returns jsonb
language plpgsql stable security definer set search_path='' as $$
begin
 if not exists(select 1 from public.moderators where user_id=auth.uid()) then raise exception 'Moderator required' using errcode='42501'; end if;
 return coalesce((select jsonb_agg(x) from (select r.*,s.title,s.is_hidden from public.content_reports r
   join public.stories s on s.id=r.story_id order by r.created_at desc limit 100) x),'[]'::jsonb);
end;
$$;
create function public.moderate_story(p_story uuid,p_hidden boolean,p_reason text) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.moderators where user_id=auth.uid()) then raise exception 'Moderator required' using errcode='42501'; end if;
 update public.stories set is_hidden=p_hidden where id=p_story;
 if not found then raise exception 'Story not found' using errcode='P0002'; end if;
 insert into public.moderation_audit(story_id,moderator_id,hidden,reason) values(p_story,auth.uid(),p_hidden,p_reason);
 update public.content_reports set status='reviewed' where story_id=p_story;
 return jsonb_build_object('story_id',p_story,'hidden',p_hidden);
end;
$$;
revoke all on function public.report_story(uuid,text,text),public.moderation_reports(),public.moderate_story(uuid,boolean,text) from public,anon;
grant execute on function public.report_story(uuid,text,text),public.moderation_reports(),public.moderate_story(uuid,boolean,text) to authenticated;

-- DB triggers also protect writes made directly with the public Supabase key.
create function public.public_write_guard() returns trigger
language plpgsql security definer set search_path='' as $$
declare v_owner uuid; v_count integer; v_limit integer;
begin
 perform pg_advisory_xact_lock(734160);
 if tg_table_name='stories' then
   v_owner:=new.owner_id; v_limit:=5;
   select count(*) into v_count from public.stories where owner_id=v_owner and created_at>now()-interval '1 day';
 elsif tg_table_name='contributions' then
   v_owner:=new.author_id; v_limit:=30;
   if not public.story_visible(new.story_id) then raise exception 'Story not found' using errcode='P0002'; end if;
   select count(*) into v_count from public.contributions where author_id=v_owner and created_at>now()-interval '1 day';
 elsif tg_table_name='chapters' then
   v_owner:=new.author_id; v_limit:=30;
   if not public.story_visible(new.story_id) then raise exception 'Story not found' using errcode='P0002'; end if;
   select count(*) into v_count from public.chapters where author_id=v_owner and created_at>now()-interval '1 day';
 elsif tg_table_name='uploads' then
   v_owner:=new.owner_id; v_limit:=20;
   select count(*) into v_count from public.uploads where owner_id=v_owner and created_at>now()-interval '1 day';
 end if;
 if v_count>=v_limit then raise exception 'WRITE_QUOTA' using errcode='P0001'; end if;
 return new;
end;
$$;
create trigger public_stories_guard before insert on public.stories for each row execute function public.public_write_guard();
create trigger public_contributions_guard before insert on public.contributions for each row execute function public.public_write_guard();
create trigger public_chapters_guard before insert on public.chapters for each row execute function public.public_write_guard();
create trigger public_uploads_guard before insert on public.uploads for each row execute function public.public_write_guard();
revoke all on function public.public_write_guard() from public,anon,authenticated,service_role;

-- Limit raw Storage objects too: otherwise clients could skip upload metadata.
-- A small hackathon instance has a hard 30-object/600-MiB theoretical ceiling
-- (20-MiB bucket maximum), including unreferenced objects. Operator cleanup is manual.
create function public.storage_capacity() returns boolean
language plpgsql security definer set search_path='' as $$
begin
 perform pg_advisory_xact_lock(734161);
 return (select count(*) from storage.objects where bucket_id='story-media')<30;
end;
$$;
revoke all on function public.storage_capacity() from public;
grant execute on function public.storage_capacity() to authenticated;
alter policy story_media_insert on storage.objects with check(bucket_id='story-media'
 and (storage.foldername(name))[1]=(select auth.uid())::text
 and cardinality(storage.foldername(name))=1 and public.storage_capacity());
create function public.storage_capacity_guard() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if new.bucket_id='story-media' and not public.storage_capacity() then
  raise exception 'WRITE_QUOTA' using errcode='P0001'; end if;
 return new;
end;
$$;
create trigger story_media_capacity before insert on storage.objects for each row execute function public.storage_capacity_guard();
revoke all on function public.storage_capacity_guard() from public,anon,authenticated,service_role;

create table public.image_workers(id uuid primary key, last_seen timestamptz not null);
create table public.image_queue(
 job_id uuid primary key references public.generation_jobs(id), source jsonb not null,
 panel_index integer not null check(panel_index between 0 and 3), seed bigint not null,
 settings jsonb not null, state text not null default 'queued' check(state in ('queued','leased','done','failed')),
 lease uuid, worker_id uuid, lease_until timestamptz, created_at timestamptz not null default now()
);
alter table public.image_workers enable row level security;
alter table public.image_queue enable row level security;
revoke all on public.image_workers,public.image_queue from public,anon,authenticated;

create function public.deployment_ready() returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object('migration',5,'moderator_assigned',exists(select 1 from public.moderators),
  'storage_private',exists(select 1 from storage.buckets where id='story-media' and not public));
$$;
revoke all on function public.deployment_ready() from public,anon,authenticated;
grant execute on function public.deployment_ready() to service_role;

create function public.image_worker_online(p_seconds integer) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.image_workers where last_seen>now()-make_interval(secs=>least(p_seconds,120)));
$$;
create function public.image_enqueue(p_job uuid,p_source jsonb,p_index integer,p_seed bigint,p_settings jsonb) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not exists(select 1 from public.generation_jobs j where j.id=p_job and j.kind='image' and j.status='running'
  and j.owner_id=(p_source->>'owner_id')::uuid and j.draft_id=(p_source->>'id')::uuid) then
   raise exception 'Invalid image reservation' using errcode='42501'; end if;
 insert into public.image_queue(job_id,source,panel_index,seed,settings) values(p_job,p_source,p_index,p_seed,p_settings);
end;
$$;
create function public.image_worker_claim(p_worker uuid,p_lease_seconds integer) returns jsonb
language plpgsql security definer set search_path='' as $$
declare v_job public.image_queue; v_old record;
begin
 perform pg_advisory_xact_lock(734159);
 insert into public.image_workers values(p_worker,now()) on conflict(id) do update set last_seen=now();
 -- Expired work is terminal. Never silently re-execute a GPU request.
 for v_old in select q.job_id,j.owner_id from public.image_queue q join public.generation_jobs j on j.id=q.job_id
   where q.state in ('queued','leased') and (j.expires_at<=now() or (q.state='leased' and q.lease_until<=now())) loop
   perform public.ai_fail(v_old.owner_id,v_old.job_id,'worker_timeout');
   update public.image_queue set state='failed' where job_id=v_old.job_id;
 end loop;
 if exists(select 1 from public.image_queue where state='leased' and lease_until>now()) then return null; end if;
 select q.* into v_job from public.image_queue q join public.generation_jobs j on j.id=q.job_id
 where q.state='queued' and j.status='running' and j.expires_at>now() order by q.created_at limit 1 for update of q;
 if not found then return null; end if;
 update public.image_queue set state='leased',lease=gen_random_uuid(),worker_id=p_worker,
 lease_until=least(now()+make_interval(secs=>least(greatest(p_lease_seconds,30),300)),
   (select expires_at from public.generation_jobs where id=v_job.job_id))
 where job_id=v_job.job_id returning * into v_job;
 return jsonb_build_object('job_id',v_job.job_id,'lease',v_job.lease,'seed',v_job.seed,
   'description',(v_job.source->'ai_data'->'panels'->v_job.panel_index)-'image',
   'appearance_context',jsonb_build_object('bible',v_job.source->'ai_data'->'bible_after','seed',v_job.seed),
   'settings',v_job.settings);
end;
$$;
create function public.image_worker_job(p_job uuid,p_lease uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare v_q public.image_queue; v_j public.generation_jobs;
begin
 select * into v_q from public.image_queue where job_id=p_job and lease=p_lease;
 select * into v_j from public.generation_jobs where id=p_job;
 if v_q.job_id is null then raise exception 'Job not found' using errcode='P0002'; end if;
 if v_j.status='succeeded' then return jsonb_build_object('status','succeeded','result_draft_id',v_j.result_draft_id); end if;
 if v_q.state<>'leased' or v_q.lease_until<=now() or v_j.status<>'running' or v_j.expires_at<=now() then
  raise exception 'Expired image lease' using errcode='40001'; end if;
 return to_jsonb(v_q) || jsonb_build_object('status','running');
end;
$$;
create function public.image_worker_finish(p_job uuid,p_lease uuid,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare v_q public.image_queue; v_j public.generation_jobs; v_result uuid;
begin
 perform pg_advisory_xact_lock(734159);
 select * into v_q from public.image_queue where job_id=p_job for update;
 perform public.image_worker_job(p_job,p_lease);
 select * into v_j from public.generation_jobs where id=p_job;
 if v_j.status='succeeded' then return jsonb_build_object('id',v_j.result_draft_id,'replayed',true); end if;
 v_result:=public.ai_finish(v_j.owner_id,p_job,p_payload,
  jsonb_build_object('model',v_q.settings->>'model','input_tokens',0,'output_tokens',0),false);
 update public.image_queue set state='done' where job_id=p_job;
 return jsonb_build_object('id',v_result,'replayed',false);
end;
$$;
create function public.image_worker_fail(p_job uuid,p_lease uuid,p_code text) returns void
language plpgsql security definer set search_path='' as $$
begin
 perform public.image_worker_job(p_job,p_lease);
 perform public.ai_fail((select owner_id from public.generation_jobs where id=p_job),p_job,left(p_code,80));
 update public.image_queue set state='failed' where job_id=p_job and state<>'done';
end;
$$;
revoke all on function public.image_worker_online(integer),public.image_enqueue(uuid,jsonb,integer,bigint,jsonb),
 public.image_worker_claim(uuid,integer),public.image_worker_job(uuid,uuid),public.image_worker_finish(uuid,uuid,jsonb),public.image_worker_fail(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.image_worker_online(integer),public.image_enqueue(uuid,jsonb,integer,bigint,jsonb),
 public.image_worker_claim(uuid,integer),public.image_worker_job(uuid,uuid),public.image_worker_finish(uuid,uuid,jsonb),public.image_worker_fail(uuid,uuid,text) to service_role;
create or replace function public.discover_stories(p_search text default '',p_genre text default null,p_sort text default 'trending',
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
    from public.stories s where not s.is_hidden and (p_genre is null or s.genre=p_genre)
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
create or replace function public.story_engagement(p_story_ids uuid[]) returns table(
  story_id uuid,like_count bigint,bookmark_count bigint,follow_count bigint,
  "like" boolean,bookmark boolean,follow boolean)
language sql stable security definer set search_path='' as $$
  select s.id,
    count(*) filter(where i.kind='like'),count(*) filter(where i.kind='bookmark'),count(*) filter(where i.kind='follow'),
    coalesce(bool_or(i.kind='like' and i.user_id=auth.uid()),false),
    coalesce(bool_or(i.kind='bookmark' and i.user_id=auth.uid()),false),
    coalesce(bool_or(i.kind='follow' and i.user_id=auth.uid()),false)
  from public.stories s left join public.story_interactions i on i.story_id=s.id
  where not s.is_hidden and s.id=any(p_story_ids[1:60]) group by s.id;
$$;


commit;
