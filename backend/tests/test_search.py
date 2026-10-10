from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.config import Settings
from backend.app.repository import Repository
from backend.app.seed import load_seed
from backend.app.schemas import DiscoverRequest
from datetime import datetime, timezone
import pytest

@pytest.fixture
def setup(tmp_path):
    settings = Settings(database_path=tmp_path / 'search.sqlite3')
    repo = Repository(settings.database_path)
    repo.initialize()
    repo.import_providers(load_seed('backend/data/providers.json'))
    return TestClient(create_app(settings)), repo

def test_directory_combined_filters_and_literal_text(setup):
    client, repo = setup
    response = client.post('/api/search', json={})
    assert response.status_code == 200
    assert response.json()['total'] == 4
    assert response.json()['directoryCounts'] == {'health': 2, 'learning': 2}
    assert client.post('/api/search', json={'category':'health','cost':'unknown'}).json()['total'] == 2
    assert client.post('/api/search', json={'query':'MEDANTA'}).json()['total'] == 1
    assert client.post('/api/search', json={'query':'%'}).json()['total'] == 0
    assert client.post('/api/search', json={'unexpected':True}).status_code == 422

def test_scope_uses_membership_not_natural_phrase_and_reports_expiry(setup):
    client, repo = setup
    now = datetime.now(timezone.utc)
    scope = repo.save_scope(DiscoverRequest(query='find child support nearby'), repo.all()[:1], now, [], 60)
    body = {'scopeId':scope.scopeId,'query':'find child support nearby'}
    result = client.post('/api/search', json=body)
    assert result.status_code == 200
    assert result.json()['total'] == 1
    assert client.post('/api/search', json=body | {'category':'learning'}).json()['total'] == 0
    assert client.post('/api/search', json={'scopeId':'0'*64}).status_code == 404
    with repo._connect(write=True) as connection:
        connection.execute("UPDATE discovery_scopes SET expires_at = '2020-01-01T00:00:00+00:00'")
    assert client.post('/api/search', json=body).status_code == 410


def test_discovery_to_scoped_search_does_not_repeat_adapter(setup):
    from backend.app.discovery import DiscoveryService
    client, repo = setup
    class Adapter:
        calls = 0
        async def retrieve(self, request):
            self.calls += 1
            return [repo.all()[0].model_dump(mode='json')]
    class Validator:
        async def validate(self, candidates, now):
            from backend.app.schemas import DiscoveryProvider
            return [DiscoveryProvider.model_validate(p) for p in candidates], []
    adapter = Adapter()
    client.app.state.discovery = DiscoveryService(repo, adapter, Validator())
    request = {'query':'help finding child health support','category':'health','area':'Gurugram'}
    response = client.post('/api/discover', json=request)
    assert response.status_code == 200
    scope = response.json()['scopeId']
    found = client.post('/api/search', json={'scopeId':scope,'query':request['query']})
    assert found.json()['items'][0]['id'] == response.json()['items'][0]['id']
    assert client.post('/api/search', json={'scopeId':scope,'cost':'free'}).json()['total'] == 0
    assert client.post('/api/discover', json=request).json()['retrievalStatus'] == 'cached'
    assert adapter.calls == 1


def test_distance_and_radius_do_not_persist_origin(setup):
    client, repo = setup
    center = repo.all()[0]
    origin = {'latitude':center.latitude,'longitude':center.longitude}
    body = {'origin':origin,'radiusKm':1}
    response = client.post('/api/search', json=body)
    assert response.status_code == 200
    assert response.json()['items'][0]['id'] == center.id
    assert response.json()['items'][0]['distanceKm'] == 0
    assert response.json()['distanceMode'] == 'approximate'
    assert all(p.distanceKm is None for p in repo.all())
    assert client.post('/api/search', json={'radiusKm':1}).status_code == 422
