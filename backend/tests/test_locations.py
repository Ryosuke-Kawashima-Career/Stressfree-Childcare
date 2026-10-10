import asyncio
import httpx
import pytest
from backend.app.evidence import SourceFetcher, location_evidence


def test_official_redirects_follow_only_approved_destinations():
    async def run():
        visited=[]
        async def handler(request):
            visited.append(str(request.url))
            if request.url.host == 'www.example.org':
                return httpx.Response(301,headers={'location':'https://example.org/center'})
            return httpx.Response(200,headers={'content-type':'text/html'},text='<p>School</p>')
        fetch=SourceFetcher(('example.org',),transport=httpx.MockTransport(handler))
        assert 'School' in await fetch('https://www.example.org/center')
        assert visited == ['https://www.example.org/center','https://example.org/center']
    asyncio.run(run())


@pytest.mark.parametrize('target',['http://example.org/center','https://127.0.0.1/private','https://other.org/center'])
def test_redirect_target_rejected_before_fetch(target):
    async def run():
        count=0
        async def handler(request):
            nonlocal count
            count+=1
            return httpx.Response(302,headers={'location':target})
        fetch=SourceFetcher(('example.org',),transport=httpx.MockTransport(handler))
        with pytest.raises(ValueError): await fetch('https://example.org/center')
        assert count == 1
    asyncio.run(run())


def test_redirect_loop_is_bounded():
    async def run():
        async def handler(request):
            return httpx.Response(302,headers={'location':'/center'})
        fetch=SourceFetcher(('example.org',),transport=httpx.MockTransport(handler))
        with pytest.raises(ValueError): await fetch('https://example.org/center')
    asyncio.run(run())


def test_published_place_coordinates_win_over_map_camera_and_other_city():
    page='Raipur https://www.google.com/maps/place/Raipur/@21.2,81.6,17z/data=!3d21.2!4d81.6 ' + 'x'*40000 + ' Gurgaon https://www.google.com/maps/place/Artemis+Gurgaon/@28.4317429,77.0716473,19z/data=!3d28.4317417!4d77.072291'
    locations=location_evidence(page)
    assert len(locations)==1
    assert (locations[0]['latitude'],locations[0]['longitude']) == (28.4317417,77.072291)
    assert locations[0]['quote'] in page


def test_jsonld_and_longitude_first_map_links_preserve_pairs():
    page='{"latitude": "28.509088", "longitude": "77.041663"} https://www.google.com/maps/dir/?data=!2m2!1d77.040637!2d28.439238'
    locations=location_evidence(page)
    assert {(v['latitude'],v['longitude']) for v in locations} == {(28.509088,77.041663),(28.439238,77.040637)}
    assert location_evidence('latitude 28.431 unrelated longitude 77.071') == []


def test_partial_service_evidence_keeps_verified_provider_only():
    from backend.tests.test_discovery import candidate, validator, NOW
    async def run():
        accepted, warnings = await validator().validate([candidate(services=['Pediatric services','Invented free surgery'])], NOW)
        assert len(accepted) == 1
        assert accepted[0].services == ['Pediatric services']
        assert warnings
    asyncio.run(run())


def test_mixed_unrelated_coordinate_quotes_rejected():
    from backend.tests.test_discovery import candidate, NOW, URL, QUOTE
    from backend.app.evidence import EvidenceValidator
    async def run():
        value = candidate()
        value['citations'][0]['fields'] = ['name','providerType','address','locality','services','relevanceReason']
        value['citations'] += [dict(url=URL,title='Other place',fields=['latitude'],quote='latitude 28.431'),dict(url=URL,title='Other place',fields=['longitude'],quote='longitude 77.071')]
        async def source(url): return QUOTE + ' latitude 28.431 other location longitude 77.071'
        accepted, warnings = await EvidenceValidator(source,('example.org',)).validate([value], NOW)
        assert accepted == [] and warnings
    asyncio.run(run())


def test_adapter_preserves_long_page_place_evidence_and_paired_quotes():
    import json
    from backend.tests.test_discovery import candidate, QUOTE, URL, wire_response, NOW
    from backend.app.ai import OpenAIWebAdapter
    from backend.app.config import Settings
    from backend.app.schemas import DiscoverRequest
    from backend.app.evidence import EvidenceValidator
    async def run():
        page=QUOTE + 'x'*40000 + ' https://www.google.com/maps/place/Sample+Hospital/data=!3d28.431!4d77.071'
        count=0
        async def source(url): return page
        async def handler(request):
            nonlocal count
            count+=1
            if count==1: return httpx.Response(200,json=wire_response('summary',True))
            body=json.loads(request.content)
            assert 'verifiedLocationEvidence' in body['input']
            assert '!3d28.431!4d77.071' in body['input']
            value=candidate()
            value['citations'][0]['fields'].remove('providerType')
            return httpx.Response(200,json=wire_response(json.dumps({'providers':[value]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records=await OpenAIWebAdapter(Settings(openai_api_key='test-key',source_domains=('example.org',)),client=client,fetch_source=source).retrieve(DiscoverRequest(query='hospital'))
        accepted,_=await EvidenceValidator(source,('example.org',)).validate(records,NOW)
        assert len(accepted)==1
        assert accepted[0].latitude==28.431 and accepted[0].longitude==77.071
    asyncio.run(run())
