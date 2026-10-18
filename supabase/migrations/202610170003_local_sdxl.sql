-- Local SDXL images use the existing uploads/storage flow and versioned drafts.
begin;
alter table public.generation_jobs drop constraint generation_jobs_kind_check;
alter table public.generation_jobs add constraint generation_jobs_kind_check check(kind in ('chapter','panel','memory','image'));

alter function public.ai_reserve(uuid,uuid,uuid,text,integer,text,jsonb) rename to ai_reserve_base;
revoke all on function public.ai_reserve_base(uuid,uuid,uuid,text,integer,text,jsonb) from public,anon,authenticated,service_role;
create function public.ai_reserve(p_owner_id uuid,p_draft_id uuid,p_request_id uuid,p_kind text,p_revision integer,p_signature text,p_limits jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform pg_advisory_xact_lock(734159);
  if p_kind='image' and not exists(select 1 from public.generation_jobs where owner_id=p_owner_id and request_id=p_request_id)
    and exists(select 1 from public.generation_jobs where kind='image' and status='running' and expires_at>now()) then
    raise exception 'AI_BUSY' using errcode='P0001';
  end if;
  return public.ai_reserve_base(p_owner_id,p_draft_id,p_request_id,p_kind,p_revision,p_signature,p_limits);
end;
$$;

alter function public.ai_finish(uuid,uuid,jsonb,jsonb,boolean) rename to ai_finish_base;
revoke all on function public.ai_finish_base(uuid,uuid,jsonb,jsonb,boolean) from public,anon,authenticated,service_role;
create function public.ai_finish(p_owner_id uuid,p_job_id uuid,p_payload jsonb,p_metadata jsonb,p_memory_only boolean default false)
returns uuid language plpgsql security definer set search_path='' as $$
declare v_ids uuid[];
begin
  select coalesce(array_agg((p->'image'->>'upload_id')::uuid),'{}'::uuid[]) into v_ids
  from jsonb_array_elements(coalesce(p_payload->'panels','[]'::jsonb)) p where p->'image' is not null;
  perform public.check_owned_uploads(v_ids,p_owner_id);
  if exists(select 1 from public.uploads where id=any(v_ids) and mime_type<>'image/png') then
    raise exception 'Generated panels must be PNGs' using errcode='22023';
  end if;
  return public.ai_finish_base(p_owner_id,p_job_id,p_payload,p_metadata,p_memory_only);
end;
$$;

-- Runs inside the existing atomic publication transaction. Manual upload IDs
-- stay separate; generated panel positions use a reserved range to avoid clashes.
create function public.publish_generated_panels() returns trigger
language plpgsql security definer set search_path='' as $$
declare v_panel jsonb; v_upload uuid; v_position integer := 1000;
begin
  for v_panel in select value from jsonb_array_elements(new.comic_prompts) loop
    v_position := v_position+1;
    if v_panel->'image' is not null then
      v_upload := (v_panel->'image'->>'upload_id')::uuid;
      if not exists(select 1 from public.uploads where id=v_upload and owner_id=new.author_id and mime_type='image/png') then
        raise exception 'Generated image ownership mismatch' using errcode='42501';
      end if;
      insert into public.panels(chapter_id,upload_id,position,caption)
      values(new.id,v_upload,v_position,coalesce(v_panel->>'caption',''));
      update public.uploads set is_public=true where id=v_upload;
    end if;
  end loop;
  return new;
end;
$$;
create trigger publish_sdxl_media after insert on public.chapters for each row execute function public.publish_generated_panels();

revoke all on function public.ai_reserve(uuid,uuid,uuid,text,integer,text,jsonb) from public,anon,authenticated;
revoke all on function public.ai_finish(uuid,uuid,jsonb,jsonb,boolean) from public,anon,authenticated;
revoke all on function public.publish_generated_panels() from public,anon,authenticated,service_role;
grant execute on function public.ai_reserve(uuid,uuid,uuid,text,integer,text,jsonb),public.ai_finish(uuid,uuid,jsonb,jsonb,boolean) to service_role;
commit;
