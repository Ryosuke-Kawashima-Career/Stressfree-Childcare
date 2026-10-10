"""Discovery orchestration: cache, admission, deadlines and single-process request guards."""
import asyncio
from datetime import datetime, timezone
import sqlite3
import time

from .errors import DiscoveryError


class DiscoveryService:
    def __init__(self, repository, adapter, validator, clock=None, timeout_seconds=30,
                 max_results=20, max_requests_per_minute=10, max_inflight=4, ttl_seconds=86400):
        self.repository, self.adapter, self.validator = repository, adapter, validator
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds, self.max_results = timeout_seconds, min(max_results, 20)
        self.max_requests_per_minute, self.max_inflight = max_requests_per_minute, max_inflight
        self.ttl_seconds = ttl_seconds
        self.sessions, self.scopes, self.starts = set(), set(), []

    async def _retrieve_and_validate(self, request, now):
        candidates = await self.adapter.retrieve(request)
        if not isinstance(candidates, list):
            raise DiscoveryError('ai_invalid_output', 'Discovery returned invalid provider information.', 502)
        warnings = []
        if len(candidates) > self.max_results:
            warnings.append('Additional results were omitted by the server result limit.')
        records, admission_warnings = await self.validator.validate(candidates[:self.max_results], now)
        if request.category != 'all':
            matching = [p for p in records if p.category == request.category]
            if len(matching) != len(records):
                warnings.append('Providers outside the requested category were omitted.')
            records = matching
        area_records = []
        for provider in records:
            address = (provider.address + ' ' + provider.locality).casefold()
            in_area = 'manesar' in address if request.area == 'Manesar' else any(area in address for area in ('gurugram', 'gurgaon', 'manesar'))
            if in_area and 28.2 <= provider.latitude <= 28.7 and 76.6 <= provider.longitude <= 77.3:
                area_records.append(provider)
            else:
                warnings.append('Providers outside the requested Gurugram/Manesar area were omitted.')
        return area_records, list(dict.fromkeys(warnings + admission_warnings))

    async def discover(self, request, session):
        self.repository.ensure_ready()
        scope_id, now = self.repository.scope_id(request), self.clock()
        saved = None
        if request.savedScopeId:
            if request.savedScopeId != self.repository.scope_id(request, 'stored-v1'):
                raise DiscoveryError('scope_mismatch', 'Stored results belong to another query or area. Submit the search again.', 422)
            saved = self.repository.scope(request.savedScopeId, now)
        # Check guards before cache: a refresh in progress must not admit another submission.
        if session in self.sessions or scope_id in self.scopes:
            raise DiscoveryError('discovery_in_progress', 'A discovery request is already running. Wait for it to finish.', 409)
        cached = None
        try:
            cached = self.repository.scope(scope_id, now)
        except DiscoveryError as error:
            if error.code not in ('scope_not_found', 'scope_expired'):
                raise
        if cached and not request.refresh:
            return cached
        start = time.monotonic()
        self.starts = [s for s in self.starts if start - s < 60]
        if len(self.sessions) >= self.max_inflight or len(self.starts) >= self.max_requests_per_minute:
            raise DiscoveryError('discovery_rate_limit', 'Discovery request limit reached. Retry shortly.', 429)
        self.sessions.add(session)
        self.scopes.add(scope_id)
        self.starts.append(start)
        task = None
        try:
            task = asyncio.create_task(self._retrieve_and_validate(request, now))
            done, _ = await asyncio.wait({task}, timeout=self.timeout_seconds)
            if not done:
                task.cancel()
                raise DiscoveryError('ai_timeout', 'Discovery timed out. Try a narrower provider search.', 504)
            records, warnings = task.result()
            if saved:
                records = list({provider.id: provider for provider in [*saved.items, *records]}.values())
            # Save only after successful bounded retrieval; cancelled work never writes a scope.
            return self.repository.save_scope(request, records, now, warnings, self.ttl_seconds)
        except DiscoveryError as error:
            if saved and saved.items:
                return saved.model_copy(update={'retrievalStatus':'stored','warnings':saved.warnings + ['AI refresh failed; showing stored providers. ' + error.message]})
            if cached:
                return cached.model_copy(update={'warnings': cached.warnings + ['Discovery refresh failed; showing previously retrieved results. ' + error.message]})
            raise
        except sqlite3.Error:
            raise DiscoveryError('database_unavailable', 'Provider database is temporarily unavailable.') from None
        finally:
            if task and not task.done():
                task.cancel()
            self.sessions.discard(session)
            self.scopes.discard(scope_id)
