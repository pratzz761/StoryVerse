"""Opt-in public API smoke test. Never runs from credentials alone.

Uses two confirmed test accounts, leaves one labeled validation story, and only
requests real AI/SDXL when their additional flags are explicitly enabled.
"""
import hashlib
import os
import time
from urllib.parse import urlparse
from uuid import uuid4
import httpx
import pytest


@pytest.mark.skipif(os.getenv('STORYVERSE_DEPLOYED_TESTS') != '1', reason='Public deployment URL, two confirmed accounts and explicit opt-in required')
def test_public_authenticated_story_generation_and_remote_images():
    from dotenv import load_dotenv
    load_dotenv(os.getenv('STORYVERSE_LIVE_ENV_FILE','.env.hosted'),override=False)
    from app.config import Settings
    config=Settings(app_mode='supabase')
    origin=os.environ['STORYVERSE_PUBLIC_API_URL'].rstrip('/')
    parsed=urlparse(origin)
    assert parsed.scheme=='https' and parsed.hostname not in ('localhost','127.0.0.1') and not parsed.username
    tokens=[]
    with httpx.Client(timeout=90,follow_redirects=False) as client:
        for account in ('A','B'):
            response=client.post(config.supabase_url.rstrip('/')+'/auth/v1/token',params={'grant_type':'password'},
                headers={'apikey':config.supabase_anon_key},json={
                    'email':os.environ['SUPABASE_TEST_EMAIL_'+account],
                    'password':os.environ['SUPABASE_TEST_PASSWORD_'+account]})
            assert response.status_code==200, 'Test account sign-in failed (credentials redacted)'
            tokens.append(response.json()['access_token'])
        a,b=[{'Authorization':'Bearer '+token} for token in tokens]
        def call(method,path,headers=None,**kwargs):return client.request(method,origin+'/api'+path,headers=headers,**kwargs)
        assert call('GET','/ready').status_code==200
        assert call('GET','/me').status_code==401
        assert call('GET','/me',a).status_code==200 and call('GET','/me',b).status_code==200
        created=call('POST','/stories',a,json={'title':'[Public validation] '+str(uuid4()),'genre':'Fantasy','narrative':'Mira finds a brass lantern on an empty wooden pier.'})
        assert created.status_code==201, 'Story creation failed'
        story=created.json()['id']
        contribution=call('POST',f'/stories/{story}/contributions',a,json={'text':'Mira discovers a blue inscription under the lantern. Keep the mystery open.','expected_version':1})
        assert contribution.status_code==201
        draft=contribution.json()['id']
        assert call('GET','/drafts/'+draft,b).status_code==404
        assert call('GET','/drafts/'+draft).status_code==401
        ai=os.getenv('STORYVERSE_DEPLOYED_AI')=='1'
        images=os.getenv('STORYVERSE_DEPLOYED_SDXL')=='1'
        assert not images or ai, 'Remote image verification requires real AI panel descriptions'
        if ai:
            generated=call('POST',f'/drafts/{draft}/generate',a,json={'request_id':str(uuid4()),'expected_revision':0,'consent':True})
            assert generated.status_code==200, 'Deployed Gemini generation failed; inspect sanitized API error code'
            draft=generated.json()['id'];data=call('GET','/drafts/'+draft,a).json()
            assert data['source']=='ai_generated' and not data['ai_data']['is_test_fixture']
            assert 2<=len(data['ai_data']['panels'])<=4
        if images:
            # Respect the production one-per-minute reservation default.
            time.sleep(62)
            queued=call('POST',f'/drafts/{draft}/panels/0/image',a,json={'request_id':str(uuid4()),'expected_revision':0,'consent':True})
            assert queued.status_code==202, 'Remote worker unavailable or queue rejected'
            job=queued.json()['job_id'];deadline=time.monotonic()+420
            while time.monotonic()<deadline:
                result=call('GET','/image-jobs/'+job,a).json()
                assert result['status']!='failed', 'Remote image job failed'
                if result['status']=='succeeded':draft=result['id'];break
                time.sleep(3)
            else:pytest.fail('Remote image job did not finish')
            image=call('GET','/drafts/'+draft,a).json()['ai_data']['panels'][0]['image']
            assert not image['is_test_fixture'] and image['transport']=='outbound_worker'
            path='/uploads/'+image['upload_id']+'/file'
            assert call('GET',path).status_code==404 and call('GET',path,b).status_code==404
            content=call('GET',path,a).content
            assert content.startswith(b'\x89PNG\r\n\x1a\n') and hashlib.sha256(content).hexdigest()==image['sha256']
        published=call('POST','/drafts/'+draft+'/publish',a,json={'expected_version':1,'approved':True})
        assert published.status_code==200, 'Explicit publication failed'
        public=call('GET','/stories/'+story).json()
        assert public['version']==2 and len(public['chapters'])==2
        if images:assert call('GET',path).content==content
