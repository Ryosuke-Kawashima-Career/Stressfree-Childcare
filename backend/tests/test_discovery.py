"""Deterministic Phase 9 contracts: no network or paid API calls."""
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.discovery import DiscoveryService, DiscoveryError
from backend.app.ai import OpenAIWebAdapter
from backend.app.evidence import EvidenceValidator
from backend.app.repository import Repository
from backend.app.schemas import DiscoverRequest
from backend.app.seed import load_seed

NOW = datetime(2026, 10, 10, tzinfo=timezone.utc)
URL = 'https://example.org/center'
QUOTE = 'Sample Hospital, Sector 51, Gurugram. Hospital. Pediatric services. Map coordinates 28.431, 77.071.'


def candidate(**changes):
    result = dict(id='model-id', name='Sample Hospital', providerType='Hospital', category='health',
        address='Sector 51, Gurugram', locality='Sector 51', latitude=28.431, longitude=77.071,
        services=['Pediatric services'], serviceTags=[], costStatus='unknown',
        sourceUrl=URL, checkedAt='2026-10-10', coordinateSourceUrl=URL,
        coordinateStatus='Approximate area location', relevanceReason='Pediatric services',
        citations=[dict(url=URL, title='Sample official location', fields=['name', 'providerType', 'address', 'locality', 'services', 'latitude', 'longitude', 'relevanceReason'], quote=QUOTE)])
    return result | changes


async def source(url):
    assert url == URL
    return QUOTE


def validator():
    return EvidenceValidator(source, allowed_domains=('example.org',))


class Stub:
    def __init__(self, records=None, error=None):
        self.calls = 0
        self.records = records if records is not None else [candidate()]
        self.error = error
    async def retrieve(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return self.records


@pytest.fixture
def repo(tmp_path):
    repository = Repository(tmp_path / 'test.sqlite3')
    repository.initialize()
    return repository


def service(repo, adapter=None, **kw):
    return DiscoveryService(repo, adapter or Stub(), validator(), clock=lambda: NOW, **kw)


def test_seed_preserves_starting_four_and_is_idempotent(repo):
    records = load_seed(Path('backend/data/providers.json'))
    repo.import_providers(records)
    repo.import_providers(records)
    assert {p.id for p in repo.all()} == {'medanta', 'artemis', 'udayan-dundahera', 'udayan-manesar'}
    assert repo.counts() == {'health': 2, 'learning': 2}
    assert all(p.coordinateSourceUrl for p in repo.all())
    assert all(not p.whatsappConfirmed for p in repo.all())


def test_import_transaction_rolls_back_bad_batch(repo):
    records = load_seed(Path('backend/data/providers.json'))
    bad = records[0].model_copy(update={'latitude': 999})
    with pytest.raises(ValueError):
        repo.import_providers([records[1], bad])
    assert repo.all() == []


def test_repository_rejects_unsupported_schema(tmp_path):
    path = tmp_path / 'future.sqlite3'
    with sqlite3.connect(path) as connection:
        connection.execute('PRAGMA user_version = 9')
    with pytest.raises(ValueError):
        Repository(path).initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 9


def test_cache_restart_dedup_and_no_raw_query(repo):
    async def run():
        adapter = Stub()
        result = await service(repo, adapter).discover(DiscoverRequest(query='Private phrase for pediatric care'), 'session')
        assert result.total == 1 and result.retrievalStatus == 'fresh'
        reopened = Repository(repo.path)
        cached = await service(reopened, adapter).discover(DiscoverRequest(query=' PRIVATE phrase for pediatric care '), 'session')
        assert cached.scopeId == result.scopeId
        assert cached.retrievalStatus == 'cached' and adapter.calls == 1
        assert cached.items[0].id != 'model-id'
        assert len(reopened.all()) == 1
        scoped = reopened.scope(result.scopeId, NOW)
        assert [p.id for p in scoped.items] == [p.id for p in result.items]
        assert b'Private phrase' not in repo.path.read_bytes()
    asyncio.run(run())


def test_scope_distinguishes_area_and_category(repo):
    request = DiscoverRequest(query='hospital')
    assert repo.scope_id(request) != repo.scope_id(request.model_copy(update={'area': 'Manesar'}))
    assert repo.scope_id(request) != repo.scope_id(request.model_copy(update={'category': 'learning'}))


def test_expiry_and_missing_scope(repo):
    async def run():
        result = await service(repo).discover(DiscoverRequest(query='hospital'), 'a')
        with pytest.raises(DiscoveryError) as missing:
            repo.scope('a' * 64, NOW)
        assert missing.value.code == 'scope_not_found'
        with pytest.raises(DiscoveryError) as expired:
            repo.scope(result.scopeId, NOW + timedelta(hours=24))
        assert expired.value.code == 'scope_expired'
        adapter = Stub()
        result = await DiscoveryService(repo, adapter, validator(), clock=lambda: NOW + timedelta(hours=25)).discover(DiscoverRequest(query='hospital'), 'a')
        assert result.retrievalStatus == 'fresh' and adapter.calls == 1
    asyncio.run(run())


def test_failed_refresh_keeps_timestamp_and_warns(repo):
    async def run():
        first = await service(repo).discover(DiscoverRequest(query='hospital'), 'a')
        cached = await service(repo, Stub(error=DiscoveryError('ai_quota', 'AI quota unavailable.', 503))).discover(DiscoverRequest(query='hospital', refresh=True), 'a')
        assert cached.retrievalStatus == 'cached' and cached.retrievedAt == first.retrievedAt
        assert 'refresh' in ' '.join(cached.warnings).lower()
    asyncio.run(run())


@pytest.mark.parametrize('changes', [
    {'citations': []}, {'latitude': 29}, {'coordinateSourceUrl': 'https://example.org/guessed'},
    {'name': 'Invented Hospital'}, {'services': ['Invented free surgery']},
    {'relevanceReason': 'Guaranteed best care'}, {'sourceUrl': 'http://127.0.0.1/private'},
    {'latitude': float('nan')}, {'isDemo': True},
])
def test_unsupported_core_evidence_rejected(changes):
    async def run():
        accepted, warnings = await validator().validate([candidate(**changes)], NOW)
        assert accepted == [] and warnings
    asyncio.run(run())


def test_source_quote_must_be_on_page():
    async def false_source(_):
        return 'A completely different provider page'
    async def run():
        accepted, warnings = await EvidenceValidator(false_source, allowed_domains=('example.org',)).validate([candidate()], NOW)
        assert not accepted and warnings
    asyncio.run(run())


def test_unsupported_optional_cost_contact_tags_are_not_admitted():
    async def run():
        accepted, warnings = await validator().validate([candidate(costStatus='free', phone='12345', serviceTags=['vaccination'], whatsappConfirmed=True, whatsappNumber='+919999999999')], NOW)
        assert len(accepted) == 1
        assert accepted[0].costStatus == 'unknown' and accepted[0].phone is None
        assert accepted[0].serviceTags == [] and accepted[0].whatsappConfirmed is False
        assert warnings
    asyncio.run(run())


def test_category_mismatch_omitted(repo):
    async def run():
        result = await service(repo).discover(DiscoverRequest(query='learning', category='learning'), 's')
        assert result.items == [] and result.total == 0 and result.warnings
    asyncio.run(run())


def test_model_id_changes_do_not_duplicate_and_confirmed_contact_survives(repo):
    async def run():
        first = await service(repo).discover(DiscoverRequest(query='hospital'), 's')
        existing = first.items[0].model_copy(update={'whatsappConfirmed': True, 'whatsappNumber': '+919876543210', 'whatsappSourceUrl': URL, 'whatsappCheckedAt': NOW.date()})
        repo.import_providers([existing])
        second = await service(repo, Stub([candidate(id='random-id')])).discover(DiscoverRequest(query='hospital', refresh=True), 's')
        assert second.items[0].id == existing.id
        assert second.items[0].whatsappConfirmed is True
        assert len(repo.all()) == 1
    asyncio.run(run())


def test_duplicate_session_and_query_guard(repo):
    async def run():
        started, release = asyncio.Event(), asyncio.Event()
        class Slow(Stub):
            async def retrieve(self, request):
                started.set()
                await release.wait()
                return [candidate()]
        orchestrator = service(repo, Slow())
        task = asyncio.create_task(orchestrator.discover(DiscoverRequest(query='hospital'), 'same'))
        await started.wait()
        for query, session in [('other request', 'same'), ('hospital', 'another')]:
            with pytest.raises(DiscoveryError) as error:
                await orchestrator.discover(DiscoverRequest(query=query), session)
            assert error.value.code == 'discovery_in_progress'
        release.set()
        await task
    asyncio.run(run())


def test_deadline_cancels_without_cache_write_and_allows_retry(repo):
    async def run():
        class Slow(Stub):
            async def retrieve(self, request):
                await asyncio.sleep(1)
                return [candidate()]
        orchestrator = service(repo, Slow(), timeout_seconds=0.01)
        with pytest.raises(DiscoveryError) as error:
            await orchestrator.discover(DiscoverRequest(query='hospital'), 's')
        assert error.value.code == 'ai_timeout' and repo.all() == []
        orchestrator.adapter = Stub()
        assert (await orchestrator.discover(DiscoverRequest(query='hospital'), 's')).total == 1
    asyncio.run(run())


def test_result_cap_and_no_unbounded_import(repo):
    async def run():
        records = [candidate(id=f'random-{i}') for i in range(21)]
        result = await service(repo, Stub(records)).discover(DiscoverRequest(query='hospital'), 's')
        assert result.total <= 20 and len(repo.all()) <= 20 and result.warnings
    asyncio.run(run())


def test_rate_limit(repo):
    async def run():
        orchestrator = service(repo, max_requests_per_minute=1)
        await orchestrator.discover(DiscoverRequest(query='first'), 's')
        with pytest.raises(DiscoveryError) as error:
            await orchestrator.discover(DiscoverRequest(query='second'), 's')
        assert error.value.status == 429
    asyncio.run(run())


def test_discover_route_and_safe_validation_errors(repo):
    client = TestClient(create_app(Settings(database_path=repo.path, openai_api_key=''), discovery_service=service(repo)))
    response = client.post('/api/discover', json={'query': 'child health'})
    assert response.status_code == 200
    body = response.json()
    assert body['retrievalStatus'] == 'fresh' and body['items'][0]['citations']
    assert body['coverage'] == 'Gurugram source-backed discovery'
    assert client.post('/api/discover', json={'query': 'child health'}).json()['retrievalStatus'] == 'cached'
    for payload in [{'query': ''}, {'query': 'a' * 121}, {'query': 'test', 'area': 'Delhi'}, {'query': 'test', 'origin': {'latitude': 28.1234567, 'longitude': 77.1234567}}, {'query': 'test', 'phone': 'secret-number'}]:
        response = client.post('/api/discover', json=payload)
        assert response.status_code == 422 and 'detail' in response.json()
        assert '28.1234567' not in response.text and 'secret-number' not in response.text
    assert client.post('/api/discover', content=b'x' * 10000, headers={'Content-Type': 'application/json'}).status_code == 413


def test_missing_credentials_error_and_absent_db(repo, tmp_path):
    client = TestClient(create_app(Settings(database_path=repo.path, openai_api_key='')))
    response = client.post('/api/discover', json={'query': 'hospital'})
    assert response.status_code == 503 and response.json()['error']['code'] == 'ai_not_configured'
    client = TestClient(create_app(Settings(database_path=tmp_path / 'missing.db', openai_api_key='')))
    assert client.post('/api/discover', json={'query': 'hospital'}).json()['error']['code'] == 'database_unavailable'


def wire_response(text, sources=False):
    output = [{'type': 'message', 'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}]
    if sources:
        output.insert(0, {'type': 'web_search_call', 'action': {'sources': [{'url': URL}]}})
    return {'id': 'resp_test', 'status': 'completed', 'output': output}


def test_adapter_two_steps_grounded_sources_and_server_only_input():
    async def run():
        requests = []
        async def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            assert body['store'] is False and 'origin' not in request.content.decode()
            if len(requests) == 1:
                assert body['tools'][0]['type'] == 'web_search'
                assert body['max_tool_calls'] <= 2
                return httpx.Response(200, json=wire_response(QUOTE, True))
            assert body['text']['format']['type'] == 'json_schema'
            assert body['text']['format']['strict'] is True
            return httpx.Response(200, json=wire_response(json.dumps({'providers': [candidate()]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIWebAdapter(Settings(openai_api_key='test-key', ai_model='configured-model'), client=client)
            result = await adapter.retrieve(DiscoverRequest(query='hospital'))
        assert len(requests) == 2 and len(result) == 1
        assert adapter.last_trace_ids == ['resp_test', 'resp_test']
    asyncio.run(run())


@pytest.mark.parametrize('status,code', [(401, 'ai_authentication'), (403, 'ai_authentication'), (429, 'ai_quota'), (500, 'ai_unavailable')])
def test_adapter_safe_upstream_errors(status, code):
    async def run():
        async def handler(_):
            return httpx.Response(status, json={'error': {'message': 'secret-key raw request body'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIWebAdapter(Settings(openai_api_key='test-key'), client=client)
            with pytest.raises(DiscoveryError) as error:
                await adapter.retrieve(DiscoverRequest(query='hospital'))
            assert error.value.code == code and 'secret' not in str(error.value)
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['no_sources', 'refusal', 'malformed', 'incomplete', 'invented_citation', 'network'])
def test_adapter_rejects_invalid_and_ungrounded_responses(kind):
    async def run():
        count = 0
        async def handler(_):
            nonlocal count
            count += 1
            if kind == 'network':
                raise httpx.ConnectError('secret upstream info')
            if count == 1 and kind != 'no_sources':
                return httpx.Response(200, json=wire_response(QUOTE, True))
            if kind == 'no_sources':
                value = wire_response(QUOTE)
            elif kind == 'refusal':
                value = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal', 'refusal': 'No'}]}]}
            elif kind == 'incomplete':
                value = {'status': 'incomplete', 'output': []}
            elif kind == 'invented_citation':
                value = wire_response(json.dumps({'providers': [candidate(citations=[dict(url='https://invented.org', title='Fake', fields=['name'], quote='fake')])]}))
            else:
                value = wire_response('not JSON')
            return httpx.Response(200, json=value)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIWebAdapter(Settings(openai_api_key='test-key'), client=client)
            with pytest.raises(DiscoveryError):
                await adapter.retrieve(DiscoverRequest(query='hospital'))
        assert count <= 2
    asyncio.run(run())

def test_default_model_search_request_avoids_unsupported_filters():
    async def run():
        async def handler(request):
            body = json.loads(request.content)
            if 'tools' in body:
                assert body['model'] == 'gpt-4.1-mini'
                assert 'filters' not in body['tools'][0]
                return httpx.Response(200, json=wire_response(QUOTE, True))
            return httpx.Response(200, json=wire_response(json.dumps({'providers': [candidate()]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await OpenAIWebAdapter(Settings(openai_api_key='test-key'), client=client).retrieve(DiscoverRequest(query='hospital'))
    asyncio.run(run())


def test_model_cannot_overwrite_seed_by_reusing_its_id(repo):
    async def run():
        repo.import_providers(load_seed(Path('backend/data/providers.json')))
        result = await service(repo, Stub([candidate(id='medanta')])).discover(DiscoverRequest(query='hospital'), 's')
        assert result.items[0].id != 'medanta'
        assert next(p for p in repo.all() if p.id == 'medanta').name == 'Medanta — The Medicity'
        assert len(repo.all()) == 5
    asyncio.run(run())

def test_extraction_schema_uses_supported_url_representation():
    from backend.app.ai import strict_schema
    schema = strict_schema()
    assert '"format": "uri"' not in json.dumps(schema)
    assert schema['$defs']['Candidate']['properties']['sourceUrl']['type'] == 'string'

def test_extraction_uses_independently_fetched_source_text():
    async def run():
        count = 0
        async def source_page(url):
            assert url == URL
            return QUOTE + ' Independently fetched page marker.'
        async def handler(request):
            nonlocal count
            count += 1
            body = json.loads(request.content)
            if count == 1:
                return httpx.Response(200, json=wire_response('A retrieved summary without the marker', True))
            assert 'Independently fetched page marker.' in body['input']
            return httpx.Response(200, json=wire_response(json.dumps({'providers': [candidate()]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIWebAdapter(Settings(openai_api_key='test-key', source_domains=('example.org',)), client=client, fetch_source=source_page)
            assert await adapter.retrieve(DiscoverRequest(query='hospital'))
    asyncio.run(run())


def test_requested_coarse_area_does_not_admit_outside_provider(repo):
    async def run():
        result = await service(repo).discover(DiscoverRequest(query='hospital', area='Manesar'), 's')
        assert result.total == 0 and result.warnings
    asyncio.run(run())

def test_page_parser_preserves_provider_published_map_iframe():
    from backend.app.evidence import PageText
    parser = PageText()
    parser.feed('<h1>Sample Hospital</h1><iframe src="https://www.google.com/maps/embed?lat=28.431&amp;lng=77.071"></iframe>')
    assert 'https://www.google.com/maps/embed?lat=28.431&lng=77.071' in ' '.join(parser.parts)

def test_page_parser_excludes_bundled_code_but_keeps_jsonld_and_text():
    from backend.app.evidence import PageText
    parser = PageText()
    parser.feed('<style>style-noise</style><script>bundled-code-noise</script><script type="application/ld+json">{"name":"Sample Hospital","latitude":28.431,"longitude":77.071}</script><p>Pediatric services</p>')
    text = ' '.join(parser.parts)
    assert 'style-noise' not in text and 'bundled-code-noise' not in text
    assert 'Sample Hospital' in text and '28.431' in text and 'Pediatric services' in text

def test_adapter_builds_verbatim_field_evidence_from_fetched_pages():
    async def run():
        count = 0
        value = candidate(citations=[dict(url=URL, title='Sample location', fields=['name', 'providerType', 'address', 'locality', 'services', 'latitude', 'longitude', 'relevanceReason'], quote='A model-composed summary that is not a verbatim source quote')])
        async def handler(request):
            nonlocal count
            count += 1
            return httpx.Response(200, json=wire_response(QUOTE, True) if count == 1 else wire_response(json.dumps({'providers': [value]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = OpenAIWebAdapter(Settings(openai_api_key='test-key', source_domains=('example.org',)), client=client, fetch_source=source)
            records = await adapter.retrieve(DiscoverRequest(query='hospital'))
        accepted, _ = await validator().validate(records, NOW)
        assert len(accepted) == 1
        assert all(c['quote'].casefold() in QUOTE.casefold() for c in records[0]['citations'])
    asyncio.run(run())

def test_adapter_drops_unsupported_type_descriptors_using_source_label():
    async def run():
        count = 0
        async def handler(request):
            nonlocal count
            count += 1
            value = candidate(providerType='Multi-specialty hospital')
            return httpx.Response(200, json=wire_response(QUOTE, True) if count == 1 else wire_response(json.dumps({'providers': [value]})))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            records = await OpenAIWebAdapter(Settings(openai_api_key='test-key', source_domains=('example.org',)), client=client, fetch_source=source).retrieve(DiscoverRequest(query='hospital'))
        accepted, _ = await validator().validate(records, NOW)
        assert len(accepted) == 1 and accepted[0].providerType == 'Hospital'
    asyncio.run(run())
