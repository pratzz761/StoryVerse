import { PGlite } from '@electric-sql/pglite';
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';

// Actual PostgreSQL execution, with minimal substitutes for Supabase-owned schemas.
// This checks migration SQL, grants, RLS, ownership, and publication invariants.
const db = new PGlite();
await db.exec(`
  create role anon nologin;
  create role authenticated nologin;
  create role service_role nologin;
  grant usage on schema public to service_role;
  create schema auth;
  create table auth.users(id uuid primary key, raw_user_meta_data jsonb not null default '{}');
  create function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid
  $$;
  grant usage on schema public,auth to anon,authenticated;
  grant execute on function auth.uid() to anon,authenticated;
  create schema storage;
  create table storage.buckets(id text primary key,name text,public boolean,file_size_limit bigint,allowed_mime_types text[]);
  create table storage.objects(id uuid default gen_random_uuid(),bucket_id text,name text);
  alter table storage.objects enable row level security;
  grant usage on schema storage to anon,authenticated;
  grant select,insert,delete on storage.objects to anon,authenticated;
  create function storage.foldername(text) returns text[] language sql immutable as $$
    select (string_to_array($1,'/'))[1:array_length(string_to_array($1,'/'),1)-1]
  $$;
`);
await db.exec(await readFile(new URL('../../supabase/migrations/202610170001_storyverse.sql', import.meta.url), 'utf8'));
await db.exec(await readFile(new URL('../../supabase/migrations/202610170002_ai_storytelling.sql', import.meta.url), 'utf8'));
await db.exec(await readFile(new URL('../../supabase/migrations/202610170003_local_sdxl.sql', import.meta.url), 'utf8'));
await db.exec(await readFile(new URL('../../supabase/migrations/202610170004_community_reading.sql', import.meta.url), 'utf8'));
const alice = '11111111-1111-4111-8111-111111111111';
const bob = '22222222-2222-4222-8222-222222222222';
await db.query(`insert into auth.users(id,raw_user_meta_data) values($1,'{"display_name":"Alice"}'),($2,'{"display_name":"Bob"}')`, [alice,bob]);
const asUser = async (id, role='authenticated') => {
  await db.exec(`reset role; set role ${role}`);
  await db.query(`select set_config('request.jwt.claim.sub',$1,false)`, [id]);
};
async function fails(fn, code) {
  let error;
  try { await fn(); } catch(e) { error = e; }
  assert.ok(error, 'Expected the database to reject this operation');
  assert.equal(error.code, code, error.message);
}
await asUser(alice);
assert.equal((await db.query('select display_name from public.profiles where id=$1',[alice])).rows[0].display_name,'Alice');
const storyId = (await db.query(`select public.create_story('A shared world','Fantasy','The opening chapter.','{}') id`)).rows[0].id;
const createDraft = async (text) => (await db.query(`select public.create_contribution_preview($1,$2,'Add a twist',1,'{}') id`,[storyId,text])).rows[0].id;
const aliceDraft = await createDraft('Alice original contribution.');
await db.query(`update public.drafts set title='Alice reviewed chapter',narrative='Alice reviewed text.' where id=$1`,[aliceDraft]);
await fails(() => db.query(`update public.drafts set base_version=2 where id=$1`,[aliceDraft]),'42501');
await fails(() => db.query(`update public.stories set version=100 where id=$1`,[storyId]),'42501');
await fails(() => db.query(`insert into public.chapters(story_id,author_id,position,title,narrative,source) values($1,$2,2,'Bypass','No','manual')`,[storyId,alice]),'42501');

const uploadId='aaaaaaaa-aaaa-4aaa-8aaa-000000000001';
await db.query(`insert into storage.objects(bucket_id,name) values('story-media',$1)`,[`${alice}/${uploadId}`]);
await db.query(`insert into public.uploads(id,owner_id,filename,mime_type,size_bytes,storage_path) values($1,$2,'image.png','image/png',100,$3)`,[uploadId,alice,`${alice}/${uploadId}`]);
await fails(() => db.query(`update public.uploads set is_public=true where id=$1`,[uploadId]),'42501');

await asUser(bob);
assert.equal((await db.query('select * from public.drafts where id=$1',[aliceDraft])).rows.length,0);
assert.equal((await db.query('select * from public.contributions')).rows.length,0);
assert.equal((await db.query('select * from public.uploads where id=$1',[uploadId])).rows.length,0);
assert.equal((await db.query('select * from storage.objects')).rows.length,0);
await fails(() => db.query(`select public.publish_chapter($1,1,true)`,[aliceDraft]),'P0002');
await fails(() => db.query(`select public.create_contribution_preview($1,'Stolen image','Keep it going',1,array[$2::uuid])`,[storyId,uploadId]),'22023');
await fails(() => db.query(`insert into storage.objects(bucket_id,name) values('story-media',$1)`,[`${alice}/stolen`]),'42501');
const bobDraft = await createDraft('Bob original contribution.');
await fails(() => db.query(`select public.create_contribution_preview($1,'Missing version','Keep it going',null,'{}')`,[storyId]),'40001');
await fails(() => db.query(`select public.publish_chapter($1,null,true)`,[bobDraft]),'40001');

await asUser('', 'anon');
assert.equal((await db.query('select * from public.stories')).rows.length,1);
assert.equal((await db.query(`select * from public.story_feed('shared',null,'trending')`)).rows.length,1);
assert.equal((await db.query(`select * from public.story_feed('shared','Mystery','recent')`)).rows.length,0);
assert.equal((await db.query(`select * from public.story_feed('%',null,'recent')`)).rows.length,0);
assert.equal((await db.query('select * from public.chapters')).rows.length,1);
await fails(() => db.query(`select * from public.drafts`),'42501');
await fails(() => db.query(`select public.publish_chapter($1,1,true)`,[aliceDraft]),'42501');
await fails(() => db.query(`select public.check_owned_uploads('{}',$1)`,[alice]),'42501');

await asUser(alice);
await fails(() => db.query(`select public.publish_chapter($1,1,false)`,[aliceDraft]),'42501');
const result=(await db.query(`select public.publish_chapter($1,1,true) result`,[aliceDraft])).rows[0].result;
assert.equal(result.version,2);
assert.equal((await db.query(`select count(*)::int n from public.chapters where story_id=$1`,[storyId])).rows[0].n,2);
await fails(() => db.query(`select public.publish_chapter($1,2,true)`,[aliceDraft]),'40001');
assert.equal((await db.query(`update public.drafts set title='No edit after publish' where id=$1 returning id`,[aliceDraft])).rows.length,0);
await asUser(bob);
await fails(() => db.query(`select public.publish_chapter($1,1,true)`,[bobDraft]),'40001');
await fails(() => db.query(`select public.publish_chapter($1,null,true)`,[bobDraft]),'40001');
assert.equal((await db.query(`select version from public.stories where id=$1`,[storyId])).rows[0].version,2);
assert.equal((await db.query(`select status from public.drafts where id=$1`,[bobDraft])).rows[0].status,'draft');

// Publishing a media attachment changes file visibility in the same transaction.
await asUser(alice);
const mediaDraft=(await db.query(`select public.create_contribution_preview($1,'An image chapter','Build the world',2,array[$2::uuid]) id`,[storyId,uploadId])).rows[0].id;
await db.query(`select public.publish_chapter($1,2,true)`,[mediaDraft]);
await asUser('', 'anon');
assert.equal((await db.query('select * from public.uploads where id=$1',[uploadId])).rows.length,1);
assert.equal((await db.query('select * from storage.objects')).rows.length,1);
assert.equal((await db.query('select * from public.panels')).rows.length,1);
// Phase 2 uses a separate backend identity for provider result writes.
await asUser(alice);
const aiStory=(await db.query(`select public.create_story('AI canon test','Fantasy','A traveler found a brass key.','{}') id`)).rows[0].id;
const inputDraft=(await db.query(`select public.create_contribution_preview($1,'A stranger arrives','Add a twist',1,'{}') id`,[aiStory])).rows[0].id;
const request='bbbbbbbb-bbbb-4bbb-8bbb-000000000001';
const limits={global_daily:100,user_daily:10,per_minute:10,concurrency:2,lease_seconds:120};
await fails(()=>db.query(`select public.ai_reserve($1,$2,$3,'chapter',0,'signature',$4)`,[alice,inputDraft,request,limits]),'42501');
await fails(()=>db.query(`update public.drafts set ai_data='{}' where id=$1`,[inputDraft]),'42501');
await asUser(bob);
assert.equal((await db.query(`select public.generation_source($1) value`,[inputDraft])).rows[0].value,null);
await asUser('', 'service_role');
const reserved=(await db.query(`select public.ai_reserve($1,$2,$3,'chapter',0,'signature',$4) job`,[alice,inputDraft,request,limits])).rows[0].job;
assert.equal(reserved.claimed,true);
assert.equal((await db.query(`select public.ai_reserve($1,$2,$3,'chapter',0,'signature',$4) job`,[alice,inputDraft,request,limits])).rows[0].job.claimed,false);
await fails(()=>db.query(`select public.ai_reserve($1,$2,'bbbbbbbb-bbbb-4bbb-8bbb-000000000002','chapter',0,'another',$3)`,[alice,inputDraft,limits]),'P0001');
const aiPayload={title:'The visitor',narrative:'A stranger in a grey coat approached the traveler, carrying news of an approaching flood.',
  provider:'gemini',model:'mocked-database-fixture',is_test_fixture:true,memory_revision:0,
  bible_after:{timeline:['Chapter 1: The beginning'],characters:[{name:'The stranger',description:'Wears a grey coat.',relationships:[]}]},
  memory:{summary:{synopsis:'A stranger brings a flood warning.',events:['A warning arrives.'],characters:['The stranger'],unresolved_plotlines:[]}},
  panels:[{description:'A traveler on a wooden bridge meets a stranger in a grey coat.',location:'Bridge',characters:['The stranger'],camera:'Wide',caption:''},{description:'A worn brass compass points into the forest at dusk.',location:'Bridge',characters:[],camera:'Close',caption:''}]};
const aiDraft=(await db.query(`select public.ai_finish($1,$2,$3,$4,false) id`,[alice,reserved.id,aiPayload,{model:'mocked',input_tokens:1500,output_tokens:700}])).rows[0].id;
await asUser(alice);
assert.equal((await db.query(`select status from public.drafts where id=$1`,[inputDraft])).rows[0].status,'draft');
assert.equal((await db.query(`select source from public.drafts where id=$1`,[aiDraft])).rows[0].source,'ai_generated');
await db.query(`update public.drafts set narrative='The final reviewed words change what happens next.' where id=$1`,[aiDraft]);
await fails(()=>db.query(`select public.publish_chapter($1,1,true)`,[aiDraft]),'40001');
await asUser('', 'service_role');
const memoryJob=(await db.query(`select public.ai_reserve($1,$2,'bbbbbbbb-bbbb-4bbb-8bbb-000000000003','memory',1,'memory',$3) job`,[alice,aiDraft,limits])).rows[0].job;
await db.query(`select public.ai_finish($1,$2,$3,$4,true)`,[alice,memoryJob.id,{...aiPayload,memory_revision:1},{model:'mocked',input_tokens:1000,output_tokens:300}]);
await asUser(alice);
const aiPublished=(await db.query(`select public.publish_chapter($1,1,true) result`,[aiDraft])).rows[0].result;
assert.equal((await db.query(`select public.publish_chapter($1,1,true) result`,[aiDraft])).rows[0].result.chapter_id,aiPublished.chapter_id);
const publishedAI=(await db.query(`select * from public.chapters where id=$1`,[aiPublished.chapter_id])).rows[0];
assert.equal(publishedAI.narrative,'The final reviewed words change what happens next.');
assert.equal(publishedAI.comic_prompts.length,2);
assert.equal(publishedAI.summary.source,'ai');
assert.equal((await db.query(`select data from public.story_bibles where story_id=$1`,[aiStory])).rows[0].data.characters[0].description,'Wears a grey coat.');
await asUser('', 'anon');
await fails(()=>db.query(`select * from public.generation_jobs`),'42501');
await fails(()=>db.query(`select public.story_context($1,'{}')`,[aiStory]),'42501');
// Optional SDXL: one global image job, owner-only result writes and private media.
await asUser(alice);
const imageStory=(await db.query(`select public.create_story('Local panel test','Fantasy','A traveler reaches a bridge.','{}') id`)).rows[0].id;
const imageInput=(await db.query(`select public.create_contribution_preview($1,'A warning at dawn','Add a twist',1,'{}') id`,[imageStory])).rows[0].id;
const imageUpload='aaaaaaaa-aaaa-4aaa-8aaa-000000000002';
await db.query(`insert into storage.objects(bucket_id,name) values('story-media',$1)`,[`${alice}/${imageUpload}`]);
await db.query(`insert into public.uploads(id,owner_id,filename,mime_type,size_bytes,storage_path) values($1,$2,'sdxl-panel.png','image/png',100,$3)`,[imageUpload,alice,`${alice}/${imageUpload}`]);
await fails(()=>db.query(`select public.ai_reserve_base($1,$2,gen_random_uuid(),'image',0,'image',$3)`,[alice,imageInput,limits]),'42501');
await asUser(bob);
const bobImageInput=(await db.query(`select public.create_contribution_preview($1,'Another warning','Add a twist',1,'{}') id`,[imageStory])).rows[0].id;
assert.equal((await db.query(`select * from public.uploads where id=$1`,[imageUpload])).rows.length,0);
await asUser('', 'service_role');
await fails(()=>db.query(`select public.ai_reserve_base($1,$2,gen_random_uuid(),'image',0,'image',$3)`,[alice,imageInput,limits]),'42501');
const imageJob=(await db.query(`select public.ai_reserve($1,$2,'bbbbbbbb-bbbb-4bbb-8bbb-000000000004','image',0,'image',$3) job`,[alice,imageInput,limits])).rows[0].job;
await fails(()=>db.query(`select public.ai_reserve($1,$2,gen_random_uuid(),'image',0,'bob-image',$3)`,[bob,bobImageInput,limits]),'P0001');
const imagePayload={...aiPayload,panels:[{...aiPayload.panels[0],image:{upload_id:imageUpload,provider:'local_sdxl',model:'mocked-sdxl',width:768,height:768,seed:42,is_test_fixture:true}},aiPayload.panels[1]]};
const imageDraft=(await db.query(`select public.ai_finish($1,$2,$3,$4,false) id`,[alice,imageJob.id,imagePayload,{model:'mocked-sdxl'}])).rows[0].id;
// Releasing Alice's reservation lets Bob reserve; he still cannot attach her file.
const bobImageJob=(await db.query(`select public.ai_reserve($1,$2,gen_random_uuid(),'image',0,'bob-image',$3) job`,[bob,bobImageInput,limits])).rows[0].job;
await fails(()=>db.query(`select public.ai_finish($1,$2,$3,$4,false)`,[bob,bobImageJob.id,imagePayload,{model:'mocked-sdxl'}]),'22023');
await db.query(`select public.ai_fail($1,$2,'fixture_ownership_rejection')`,[bob,bobImageJob.id]);
await asUser('', 'anon');
assert.equal((await db.query(`select * from public.uploads where id=$1`,[imageUpload])).rows.length,0);
assert.equal((await db.query(`select * from storage.objects where name=$1`,[`${alice}/${imageUpload}`])).rows.length,0);
await asUser(alice);
const imagePublished=(await db.query(`select public.publish_chapter($1,1,true) result`,[imageDraft])).rows[0].result;
await asUser('', 'anon');
assert.equal((await db.query(`select * from public.uploads where id=$1`,[imageUpload])).rows.length,1);
assert.equal((await db.query(`select * from storage.objects where name=$1`,[`${alice}/${imageUpload}`])).rows.length,1);
const imagePanels=(await db.query(`select * from public.panels where chapter_id=$1`,[imagePublished.chapter_id])).rows;
assert.equal(imagePanels.length,1);
assert.equal(imagePanels[0].position,1001);
assert.equal(imagePanels[0].upload_id,imageUpload);
assert.equal((await db.query(`select comic_prompts from public.chapters where id=$1`,[imagePublished.chapter_id])).rows[0].comic_prompts[0].image.seed,42);
// Phase 3 actions are idempotent, private per-reader rows with public aggregates.
await asUser(alice);
const liked=(await db.query(`select public.set_story_interaction($1,'like',true) value`,[imageStory])).rows[0].value;
assert.equal(liked.like_count,1);
assert.equal((await db.query(`select public.set_story_interaction($1,'like',true) value`,[imageStory])).rows[0].value.like_count,1);
await db.query(`select public.set_story_interaction($1,'bookmark',true),public.set_story_interaction($1,'follow',true)`,[imageStory]);
await fails(()=>db.query(`insert into public.story_interactions(user_id,story_id,kind) values($1,$2,'like')`,[bob,imageStory]),'42501');
await fails(()=>db.query(`select public.set_story_interaction($1,'invalid',true)`,[imageStory]),'22023');
const firstChapter=(await db.query(`select id from public.chapters where story_id=$1 order by position limit 1`,[imageStory])).rows[0].id;
await db.query(`select public.save_reading_progress($1,$2,true,'comic')`,[imageStory,firstChapter]);
const reading=(await db.query(`select public.save_reading_progress($1,$2,true,'comic') value`,[imageStory,firstChapter])).rows[0].value;
assert.equal(reading.completed_position,1);
assert.equal((await db.query(`select count(*)::int n from public.reading_progress`)).rows[0].n,1);
await fails(()=>db.query(`update public.reading_progress set user_id=$1`,[bob]),'42501');
await fails(()=>db.query(`select public.save_reading_progress($1,$2,true,'comic')`,[aiStory,firstChapter]),'22023');
await asUser(bob);
assert.equal((await db.query(`select * from public.reading_progress`)).rows.length,0);
assert.equal((await db.query(`select * from public.story_interactions`)).rows.length,0);
assert.equal((await db.query(`select public.set_story_interaction($1,'like',false) value`,[imageStory])).rows[0].value.like_count,1);
assert.equal((await db.query(`select public.set_story_interaction($1,'like',true) value`,[imageStory])).rows[0].value.like_count,2);
await asUser('', 'anon');
await fails(()=>db.query(`select * from public.story_interactions`),'42501');
await fails(()=>db.query(`select * from public.reading_progress`),'42501');
await fails(()=>db.query(`select public.set_story_interaction($1,'like',true)`,[imageStory]),'42501');
await fails(()=>db.query(`select public.save_reading_progress($1,$2,true,'comic')`,[imageStory,firstChapter]),'42501');
const publicCounts=(await db.query(`select * from public.story_engagement(array[$1::uuid])`,[imageStory])).rows[0];
assert.equal(Number(publicCounts.like_count),2);
assert.equal(publicCounts.bookmark,false);
const discovery=(await db.query(`select public.discover_stories('Local panel',null,'trending',1,1) value`)).rows[0].value;
assert.equal(discovery.total,1);
assert.equal(discovery.items[0].id,imageStory);
assert.equal(discovery.items[0].like_count,2);
assert.equal(discovery.has_next,false);
assert.equal((await db.query(`select public.discover_stories('%',null,'trending',1,12) value`)).rows[0].value.total,0);
const pageOne=(await db.query(`select public.discover_stories('',null,'trending',1,1) value`)).rows[0].value;
const pageTwo=(await db.query(`select public.discover_stories('',null,'trending',2,1) value`)).rows[0].value;
assert.equal(pageOne.items[0].id,imageStory);
assert.notEqual(pageOne.items[0].id,pageTwo.items[0].id);
await fails(()=>db.query(`select public.discover_stories('',null,'trending',0,12)`),'22023');
await asUser(alice);
await db.query(`select public.set_story_interaction($1,'bookmark',false),public.set_story_interaction($1,'follow',false)`,[imageStory]);
assert.equal((await db.query(`select * from public.story_interactions where kind in ('bookmark','follow')`)).rows.length,0);
// New optional character fields enrich canon without rewriting published prose.
const canonStory=(await db.query(`select public.create_story('Visual canon','Fantasy','The traveler wore a grey coat.','{}') id`)).rows[0].id;
for (const [index,visual] of ['', 'A grey coat and brass compass.', 'A red spacesuit.'].entries()) {
  await asUser(alice);
  const prior=(await db.query(`select data from public.story_bibles where story_id=$1`,[canonStory])).rows[0].data;
  const source=(await db.query(`select public.create_contribution_preview($1,'The traveler returns','Keep it going',$2,'{}') id`,[canonStory,index+1])).rows[0].id;
  const canonPayload={...aiPayload,bible_after:{...prior,characters:[{name:'The traveler',description:'A traveler with a compass.',
    relationships:[],personality_traits:['Patient'],visual_description:visual}]}};
  await asUser('', 'service_role');
  const job=(await db.query(`select public.ai_reserve($1,$2,gen_random_uuid(),'chapter',0,$3,$4) job`,[alice,source,`canon-${index}`,{...limits,user_daily:100,per_minute:100}])).rows[0].job;
  const draft=(await db.query(`select public.ai_finish($1,$2,$3,$4,false) id`,[alice,job.id,canonPayload,{model:'mocked-canon'}])).rows[0].id;
  await asUser(alice);
  if (index===2) await fails(()=>db.query(`select public.publish_chapter($1,$2,true)`,[draft,index+1]),'22023');
  else await db.query(`select public.publish_chapter($1,$2,true)`,[draft,index+1]);
}
assert.equal((await db.query(`select version from public.stories where id=$1`,[canonStory])).rows[0].version,3);
assert.equal((await db.query(`select narrative from public.chapters where story_id=$1 and position=1`,[canonStory])).rows[0].narrative,'The traveler wore a grey coat.');
assert.equal((await db.query(`select data from public.story_bibles where story_id=$1`,[canonStory])).rows[0].data.characters[0].visual_description,'A grey coat and brass compass.');
await (await import('./phase4-database.mjs')).phase4(db, asUser, fails);
await db.close();
console.log('PASS: all five migrations; original publication/AI/storage policies; private community and reading rows; owner-only writes; duplicate actions; accurate public counts; deterministic paginated discovery and chapter/story validation.');
