-- Additive Phase 2 migration. Existing Phase 1 data and grants are preserved.
begin;

alter table public.drafts drop constraint drafts_contribution_id_key;
alter table public.drafts drop constraint drafts_source_check;
alter table public.drafts add constraint drafts_source_check check(source in ('demo_preview','ai_generated'));
alter table public.drafts add column revision integer not null default 0;
alter table public.drafts add column parent_draft_id uuid references public.drafts(id);
alter table public.drafts add column ai_data jsonb not null default '{}' check(octet_length(ai_data::text)<=70000);
alter table public.chapters drop constraint chapters_source_check;
alter table public.chapters add constraint chapters_source_check check(source in ('manual','sample','demo_preview','ai_generated'));
alter table public.chapters add column summary jsonb not null default '{}';
alter table public.chapters add column comic_prompts jsonb not null default '[]';
alter table public.chapters add column ai_metadata jsonb not null default '{}';

create table public.story_bibles (
  story_id uuid primary key references public.stories(id),
  version integer not null default 0,
  data jsonb not null default '{}',
  updated_at timestamptz not null default now()
);
create table public.generation_jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id),
  draft_id uuid not null references public.drafts(id),
  request_id uuid not null,
  kind text not null check(kind in ('chapter','panel','memory')),
  revision integer not null,
  signature text not null,
  status text not null default 'running' check(status in ('running','succeeded','failed')),
  expires_at timestamptz not null,
  result_draft_id uuid references public.drafts(id),
  error_code text,
  model text,
  input_tokens integer,
  output_tokens integer,
  created_at timestamptz not null default now(),
  unique(owner_id,request_id)
);
create index generation_jobs_quota_idx on public.generation_jobs(owner_id,created_at);
create index generation_jobs_active_idx on public.generation_jobs(status,expires_at);
alter table public.story_bibles enable row level security;
alter table public.generation_jobs enable row level security;
revoke all on public.story_bibles,public.generation_jobs from anon,authenticated;
grant select on public.story_bibles to anon,authenticated;
grant select on public.generation_jobs to authenticated;
create policy story_bible_public on public.story_bibles for select using(true);
create policy jobs_owner_read on public.generation_jobs for select to authenticated using(owner_id=(select auth.uid()));

update public.chapters set summary=jsonb_build_object('synopsis',left(narrative,600),'events','[]'::jsonb,'characters','[]'::jsonb,'unresolved_plotlines','[]'::jsonb,'source','extractive');
insert into public.story_bibles(story_id,version,data)
select s.id,s.version,jsonb_build_object('timeline',coalesce((select jsonb_agg('Chapter ' || c.position || ': ' || c.title order by c.position) from public.chapters c where c.story_id=s.id),'[]'::jsonb)) from public.stories s;

create function public.draft_revision() returns trigger
language plpgsql set search_path='' as $$
begin
  if new.title is distinct from old.title or new.narrative is distinct from old.narrative then
    new.revision := old.revision+1;
  end if;
  return new;
end;
$$;
create trigger draft_content_revision before update on public.drafts for each row execute function public.draft_revision();

-- Only canonical additions are accepted. Existing facts must remain contained
-- in the new Bible. This runs in the same transaction as chapter publication.
create function public.chapter_memory() returns trigger
language plpgsql security definer set search_path='' as $$
declare v_old jsonb; v_data jsonb; v_ai jsonb; v_line text;
begin
  insert into public.story_bibles(story_id) values(new.story_id) on conflict do nothing;
  select data into v_old from public.story_bibles where story_id=new.story_id for update;
  v_data := v_old;
  if new.source='ai_generated' then
    select ai_data into v_ai from public.drafts where id=new.draft_id;
    v_data := v_ai->'bible_after';
    if v_data is null or not (v_data @> v_old) or octet_length(v_data::text)>16000 then
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
create trigger chapter_canonical_memory before insert on public.chapters for each row execute function public.chapter_memory();

create function public.generation_source(p_draft_id uuid) returns jsonb
language sql stable security invoker set search_path='' as $$
  select to_jsonb(d) || jsonb_build_object('contribution',to_jsonb(c))
  from public.drafts d join public.contributions c on c.id=d.contribution_id
  where d.id=p_draft_id and d.owner_id=auth.uid();
$$;

create function public.story_context(p_story_id uuid,p_terms text[] default '{}') returns jsonb
language sql stable security invoker set search_path='' as $$
  select jsonb_build_object('story',jsonb_build_object('id',s.id,'title',s.title,'genre',s.genre,'version',s.version),
    'bible',coalesce((select b.data from public.story_bibles b where b.story_id=s.id),'{}'::jsonb),
    'opening',(select left(c.narrative,1800) from public.chapters c where c.story_id=s.id order by c.position limit 1),
    'outline',coalesce((select jsonb_agg(jsonb_build_object('position',c.position,'title',c.title,'summary',c.summary) order by c.position) from public.chapters c where c.story_id=s.id),'[]'::jsonb),
    'selected',coalesce((select jsonb_agg(to_jsonb(chosen)) from (
      select c.position,c.title,left(c.narrative,3000) narrative from public.chapters c
      where c.story_id=s.id and c.position>s.version-3
      union
      (select c.position,c.title,left(c.narrative,3000) narrative from public.chapters c
       where c.story_id=s.id and c.position<=s.version-3
       order by (select count(*) from unnest(p_terms[1:8]) t where strpos(lower(c.narrative),lower(t))>0) desc,c.position desc limit 2)
    ) chosen),'[]'::jsonb)) from public.stories s where s.id=p_story_id;
$$;

-- Reservation is global to the database, including multiple API workers.
-- Only the backend's service identity may reserve/finish/fail jobs. Client JWTs
-- cannot fabricate a provider result or bypass rate limits.
create function public.ai_reserve(p_owner_id uuid,p_draft_id uuid,p_request_id uuid,p_kind text,p_revision integer,p_signature text,p_limits jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare v_d public.drafts; v_job public.generation_jobs; v_today timestamptz; v_active integer;
begin
  perform pg_advisory_xact_lock(734159);
  select * into v_d from public.drafts where id=p_draft_id and owner_id=p_owner_id;
  if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
  select * into v_job from public.generation_jobs where owner_id=p_owner_id and request_id=p_request_id;
  if found then
    if v_job.signature is distinct from p_signature then raise exception 'Request mismatch' using errcode='40001'; end if;
    return to_jsonb(v_job) || jsonb_build_object('claimed',false);
  end if;
  if v_d.status<>'draft' or v_d.revision is distinct from p_revision or v_d.base_version<>(select version from public.stories where id=v_d.story_id) then
    raise exception 'Stale draft' using errcode='40001';
  end if;
  if exists(select 1 from public.generation_jobs where owner_id=p_owner_id and status='running' and expires_at>now()) then
    raise exception 'AI_BUSY' using errcode='P0001';
  end if;
  v_today := date_trunc('day',now() at time zone 'UTC') at time zone 'UTC';
  select count(*) into v_active from public.generation_jobs where status='running' and expires_at>now();
  if (select count(*) from public.generation_jobs where created_at>=v_today)>=(p_limits->>'global_daily')::integer
    or (select count(*) from public.generation_jobs where owner_id=p_owner_id and created_at>=v_today)>=(p_limits->>'user_daily')::integer
    or (select count(*) from public.generation_jobs where owner_id=p_owner_id and created_at>now()-interval '1 minute')>=(p_limits->>'per_minute')::integer
    or v_active>=(p_limits->>'concurrency')::integer then
    raise exception 'AI_QUOTA' using errcode='P0001';
  end if;
  insert into public.generation_jobs(owner_id,draft_id,request_id,kind,revision,signature,expires_at)
  values(p_owner_id,p_draft_id,p_request_id,p_kind,p_revision,p_signature,now()+make_interval(secs=>(p_limits->>'lease_seconds')::integer)) returning * into v_job;
  return to_jsonb(v_job) || jsonb_build_object('claimed',true);
end;
$$;

create function public.ai_finish(p_owner_id uuid,p_job_id uuid,p_payload jsonb,p_metadata jsonb,p_memory_only boolean default false)
returns uuid language plpgsql security definer set search_path='' as $$
declare v_j public.generation_jobs; v_d public.drafts; v_id uuid;
begin
  select * into v_j from public.generation_jobs where id=p_job_id and owner_id=p_owner_id for update;
  if not found then raise exception 'Job not found' using errcode='P0002'; end if;
  select * into v_d from public.drafts where id=v_j.draft_id and owner_id=p_owner_id for update;
  if v_j.status<>'running' or v_j.expires_at<now() or v_d.status<>'draft' or v_d.revision<>v_j.revision then
    raise exception 'Draft changed during generation' using errcode='40001';
  end if;
  perform 1 from public.stories where id=v_d.story_id and version=v_d.base_version for share;
  if not found then raise exception 'Story changed during generation' using errcode='40001'; end if;
  if p_memory_only then
    update public.drafts set ai_data=ai_data || p_payload where id=v_d.id;
    v_id := v_d.id;
  else
    insert into public.drafts(story_id,owner_id,contribution_id,title,narrative,base_version,upload_ids,parent_draft_id,source,ai_data)
    values(v_d.story_id,p_owner_id,v_d.contribution_id,p_payload->>'title',p_payload->>'narrative',v_d.base_version,v_d.upload_ids,v_d.id,'ai_generated',p_payload)
    returning id into v_id;
  end if;
  update public.generation_jobs set status='succeeded',result_draft_id=v_id,model=p_metadata->>'model',
    input_tokens=(p_metadata->>'input_tokens')::integer,output_tokens=(p_metadata->>'output_tokens')::integer where id=v_j.id;
  return v_id;
end;
$$;

create function public.ai_fail(p_owner_id uuid,p_job_id uuid,p_code text) returns void
language sql security definer set search_path='' as $$
  update public.generation_jobs set status='failed',error_code=left(p_code,80) where id=p_job_id and owner_id=p_owner_id and status='running';
$$;

create or replace function public.reset_demo_preview(p_draft_id uuid) returns void
language plpgsql security definer set search_path='' as $$
declare v_d public.drafts;
begin
  select * into v_d from public.drafts where id=p_draft_id and owner_id=auth.uid() for update;
  if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
  if v_d.status<>'draft' or v_d.source<>'demo_preview' then raise exception 'Use versioned AI regeneration' using errcode='40001'; end if;
  update public.drafts set title='Chapter ' || (base_version+1),
    narrative=(select btrim(text) from public.contributions where id=v_d.contribution_id) where id=v_d.id;
end;
$$;

create or replace function public.publish_chapter(p_draft_id uuid,p_expected_version integer,p_approved boolean)
returns jsonb language plpgsql security definer set search_path='' as $$
declare v_draft public.drafts; v_story public.stories; v_chapter uuid;
begin
  if auth.uid() is null or p_approved is distinct from true then raise exception 'Explicit approval required' using errcode='42501'; end if;
  select * into v_draft from public.drafts where id=p_draft_id and owner_id=auth.uid() for update;
  if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
  if v_draft.status='published' and v_draft.source='ai_generated' and v_draft.base_version=p_expected_version then
    select id into v_chapter from public.chapters where draft_id=v_draft.id;
    return jsonb_build_object('story_id',v_draft.story_id,'chapter_id',v_chapter,'version',v_draft.base_version+1);
  end if;
  select * into v_story from public.stories where id=v_draft.story_id for update;
  if v_draft.status<>'draft' or v_story.version is distinct from p_expected_version or v_draft.base_version is distinct from p_expected_version then
    raise exception 'Publication conflict' using errcode='40001';
  end if;
  if v_draft.source='ai_generated' and (v_draft.ai_data->>'memory_revision')::integer is distinct from v_draft.revision then
    raise exception 'Review analysis required' using errcode='40001';
  end if;
  if char_length(btrim(v_draft.narrative))=0 then raise exception 'Narrative required' using errcode='22023'; end if;
  perform public.check_owned_uploads(v_draft.upload_ids,auth.uid());
  insert into public.chapters(story_id,author_id,draft_id,position,title,narrative,upload_ids,source)
  values(v_story.id,auth.uid(),v_draft.id,v_story.version+1,v_draft.title,v_draft.narrative,v_draft.upload_ids,v_draft.source) returning id into v_chapter;
  insert into public.panels(chapter_id,upload_id,position,caption)
  select v_chapter,u.id,row_number() over(order by array_position(v_draft.upload_ids,u.id)),u.filename
  from public.uploads u where u.id=any(v_draft.upload_ids) and u.mime_type like 'image/%';
  update public.stories set version=version+1,updated_at=now() where id=v_story.id;
  update public.drafts set status='published' where id=v_draft.id;
  update public.uploads set is_public=true where id=any(v_draft.upload_ids);
  return jsonb_build_object('story_id',v_story.id,'chapter_id',v_chapter,'version',v_story.version+1);
end;
$$;

revoke all on function public.draft_revision() from public,anon,authenticated;
revoke all on function public.chapter_memory() from public,anon,authenticated;
revoke all on function public.generation_source(uuid) from public,anon,authenticated;
revoke all on function public.story_context(uuid,text[]) from public,anon,authenticated;
grant execute on function public.generation_source(uuid),public.story_context(uuid,text[]) to authenticated;
revoke all on function public.ai_reserve(uuid,uuid,uuid,text,integer,text,jsonb) from public,anon,authenticated;
revoke all on function public.ai_finish(uuid,uuid,jsonb,jsonb,boolean) from public,anon,authenticated;
revoke all on function public.ai_fail(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.ai_reserve(uuid,uuid,uuid,text,integer,text,jsonb),public.ai_finish(uuid,uuid,jsonb,jsonb,boolean),public.ai_fail(uuid,uuid,text) to service_role;
commit;
