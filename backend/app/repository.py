"""Transactional SQLite provider directory and hashed, expiring discovery scopes."""
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.parse import urlparse

from .database import SCHEMA_VERSION
from .errors import DiscoveryError
from .schemas import DiscoverRequest, DiscoveryProvider, DiscoveryResponse


def normalized(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def identity(provider: DiscoveryProvider) -> str:
    # Identity is independent of the model's result ID, ordering and map precision.
    host = urlparse(str(provider.website or provider.sourceUrl)).hostname or ''
    host = host.removeprefix('www.')
    name = re.sub(r'[^\w]+', ' ', normalized(provider.name)).strip()
    address = re.sub(r'[^\w]+', ' ', normalized(provider.address)).strip()
    return '|'.join((host, name, address))


def stable_id(provider: DiscoveryProvider) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', normalized(provider.name)).strip('-')[:48] or 'provider'
    return slug + '-' + hashlib.sha256(identity(provider).encode()).hexdigest()[:12]


class Repository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self, write=False):
        if write:
            return sqlite3.connect(self.path, timeout=1)
        return sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect(write=True)) as connection, connection:
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version not in (0, SCHEMA_VERSION) or (version == 0 and tables):
                raise ValueError('Unsupported database schema; no changes made.')
            if 'providers' in tables:
                columns = {row[1] for row in connection.execute('PRAGMA table_info(providers)')}
                if not {'id', 'identity', 'payload', 'services', 'service_tags', 'languages'} <= columns:
                    raise ValueError('Unsupported provider schema; no changes made.')
            connection.execute('CREATE TABLE IF NOT EXISTS providers (id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, services TEXT NOT NULL, service_tags TEXT NOT NULL, languages TEXT NOT NULL)')
            connection.execute('CREATE TABLE IF NOT EXISTS discovery_scopes (scope_id TEXT PRIMARY KEY, retrieved_at TEXT NOT NULL, expires_at TEXT NOT NULL, provider_ids TEXT NOT NULL, items TEXT NOT NULL, warnings TEXT NOT NULL)')
            connection.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    def ensure_ready(self):
        try:
            with closing(self._connect()) as connection:
                if connection.execute('PRAGMA user_version').fetchone()[0] != SCHEMA_VERSION:
                    raise sqlite3.DatabaseError()
                connection.execute('SELECT id, identity, payload, services, service_tags, languages FROM providers LIMIT 1')
                connection.execute('SELECT scope_id, retrieved_at, expires_at, provider_ids, items, warnings FROM discovery_scopes LIMIT 1')
        except sqlite3.Error:
            raise DiscoveryError('database_unavailable', 'Provider database is not ready.') from None

    @staticmethod
    def _decode(row):
        payload, services, tags, languages = row
        data = json.loads(payload)
        data.update(services=json.loads(services), serviceTags=json.loads(tags), languages=json.loads(languages))
        return DiscoveryProvider.model_validate(data)

    def all(self):
        with closing(self._connect()) as connection:
            return [self._decode(row) for row in connection.execute('SELECT payload, services, service_tags, languages FROM providers ORDER BY id')]

    def counts(self):
        records = self.all()
        return {category: sum(p.category == category for p in records) for category in ('health', 'learning')}

    @staticmethod
    def scope_id(request: DiscoverRequest, purpose='discovery-v1') -> str:
        value = json.dumps([normalized(request.query), request.category, request.area, purpose], ensure_ascii=False)
        return hashlib.sha256(value.encode()).hexdigest()

    def _upsert(self, connection, provider, preserve_id=False):
        record = DiscoveryProvider.model_validate(provider.model_dump(mode='json'))
        if record.whatsappConfirmed and not (record.whatsappNumber and record.whatsappSourceUrl and record.whatsappCheckedAt):
            raise ValueError('Confirmed WhatsApp metadata is incomplete.')
        key = identity(record)
        lookup = 'identity = ? OR id = ?' if preserve_id else 'identity = ?'
        parameters = (key, record.id) if preserve_id else (key,)
        existing = connection.execute('SELECT payload, services, service_tags, languages FROM providers WHERE ' + lookup, parameters).fetchone()
        if existing:
            previous = self._decode(existing)
            record.id = previous.id
            if previous.whatsappConfirmed and not record.whatsappConfirmed:
                for field in ('whatsappConfirmed', 'whatsappNumber', 'whatsappSourceUrl', 'whatsappCheckedAt'):
                    setattr(record, field, getattr(previous, field))
        elif not preserve_id:
            record.id = stable_id(record)
        payload = record.model_dump(mode='json', exclude={'services', 'serviceTags', 'languages', 'distanceKm'})
        connection.execute('INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET identity=excluded.identity, payload=excluded.payload, services=excluded.services, service_tags=excluded.service_tags, languages=excluded.languages',
            (record.id, key, json.dumps(payload, ensure_ascii=False), json.dumps(record.services), json.dumps(record.serviceTags), json.dumps(record.languages)))
        return record

    def import_providers(self, providers):
        # Validate the complete batch before entering a write transaction.
        records = [DiscoveryProvider.model_validate(p.model_dump(mode='json') if hasattr(p, 'model_dump') else p) for p in providers]
        if len({p.id for p in records}) != len(records):
            raise ValueError('Duplicate provider IDs in import.')
        with closing(self._connect(write=True)) as connection, connection:
            return [self._upsert(connection, p, preserve_id=True) for p in records]

    def save_scope(self, request, providers, now, warnings, ttl_seconds=86400, purpose='discovery-v1', status='fresh'):
        with closing(self._connect(write=True)) as connection, connection:
            records, seen = [], set()
            for provider in providers:
                record = self._upsert(connection, provider)
                if record.id not in seen:
                    records.append(record)
                    seen.add(record.id)
            scope_id = self.scope_id(request, purpose)
            connection.execute('INSERT INTO discovery_scopes VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(scope_id) DO UPDATE SET retrieved_at=excluded.retrieved_at, expires_at=excluded.expires_at, provider_ids=excluded.provider_ids, items=excluded.items, warnings=excluded.warnings',
                (scope_id, now.isoformat(), (now + timedelta(seconds=ttl_seconds)).isoformat(), json.dumps([p.id for p in records]), json.dumps([p.model_dump(mode='json') for p in records], ensure_ascii=False), json.dumps(warnings)))
        return self.scope(scope_id, now, status=status)

    def scope(self, scope_id, now, status='cached'):
        with closing(self._connect()) as connection:
            row = connection.execute('SELECT retrieved_at, expires_at, items, warnings FROM discovery_scopes WHERE scope_id = ?', (scope_id,)).fetchone()
        if not row:
            raise DiscoveryError('scope_not_found', 'Discovery scope was not found. Submit the search again.', 404)
        retrieved, expires, items, warnings = row
        if now >= datetime.fromisoformat(expires):
            raise DiscoveryError('scope_expired', 'Discovery scope expired. Submit the search again.', 410)
        records = [DiscoveryProvider.model_validate(p) for p in json.loads(items)]
        return DiscoveryResponse(items=records, total=len(records), directoryCounts=self.counts(), scopeId=scope_id, retrievedAt=retrieved, retrievalStatus=status, warnings=json.loads(warnings))
