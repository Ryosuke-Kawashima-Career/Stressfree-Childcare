from backend.tests.test_search import setup
from backend.app.schemas import DiscoverRequest
from backend.app.errors import DiscoveryError
import pytest
import asyncio
from backend.tests.test_discovery import Stub, validator
from backend.app.discovery import DiscoveryService


def test_blank_reveals_saved_hospitals_in_an_independent_scope(setup):
    client, repo = setup
    response = client.post('/api/reveal', json={'query':'','category':'health','area':'Gurugram'})
    assert response.status_code == 200
    body = response.json()
    assert body['retrievalStatus'] == 'stored'
    assert {p['id'] for p in body['items']} == {'medanta','artemis'}
    assert client.post('/api/search',json={'scopeId':body['scopeId'],'cost':'unknown'}).json()['total']==2
    assert client.post('/api/search',json={'scopeId':body['scopeId'],'cost':'free'}).json()['total']==0


def test_aliases_plural_tokens_and_no_unrelated_fallback(setup):
    client, repo = setup
    assert client.post('/api/reveal',json={'query':'hospitals in Gurgaon'}).json()['total']==2
    assert client.post('/api/reveal',json={'query':'find Artemis hospital in Gurugram'}).json()['total']==1
    assert client.post('/api/reveal',json={'query':'unmatched-provider-zzzz'}).json()['total']==0
    assert client.post('/api/reveal',json={'query':'','category':'learning','area':'Manesar'}).json()['total']==1


def test_stored_search_does_not_poison_ai_query_cache(setup):
    client, repo = setup
    request={'query':'hospitals','category':'health','area':'Gurugram'}
    response=client.post('/api/reveal',json=request)
    assert response.status_code==200
    assert response.json()['scopeId'] != repo.scope_id(DiscoverRequest(**request))
    assert client.post('/api/reveal',json={'unexpected':True}).status_code==422


@pytest.mark.parametrize('failure', [False, True])
def test_refresh_unions_saved_members_and_failure_retains_them(setup, failure):
    client, repo = setup
    saved = client.post('/api/reveal',json={'query':'hospitals','category':'health'}).json()
    adapter = Stub(error=DiscoveryError('ai_quota','AI quota unavailable.',503) if failure else None)
    service = DiscoveryService(repo,adapter,validator())
    result = asyncio.run(service.discover(DiscoverRequest(query='hospitals',category='health',refresh=True,savedScopeId=saved['scopeId']), 'test'))
    assert {'medanta','artemis'} <= {p.id for p in result.items}
    assert result.total == (2 if failure else 3)
    assert result.retrievalStatus == ('stored' if failure else 'fresh')
    assert adapter.calls == 1
    if failure:
        assert 'AI refresh failed' in ' '.join(result.warnings)
    assert client.post('/api/search',json={'scopeId':result.scopeId}).json()['total'] == result.total


def test_refresh_rejects_scope_from_another_phrase(setup):
    client, repo = setup
    saved=client.post('/api/reveal',json={'query':'hospitals'}).json()
    adapter=Stub()
    with pytest.raises(DiscoveryError) as error:
        asyncio.run(DiscoveryService(repo,adapter,validator()).discover(DiscoverRequest(query='Artemis',refresh=True,savedScopeId=saved['scopeId']),'test'))
    assert error.value.code == 'scope_mismatch'
    assert adapter.calls == 0
