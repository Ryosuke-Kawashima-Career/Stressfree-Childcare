"""Deterministic directory/scope filters; no AI calls or origin persistence."""
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from .repository import normalized
from .schemas import DirectorySearchResponse


def search(repository, request):
    repository.ensure_ready()
    records = repository.scope(request.scopeId, datetime.now(timezone.utc)).items if request.scopeId else repository.all()
    query = '' if request.scopeId else normalized(request.query)
    items = []
    for record in records:
        text = normalized(' '.join([record.name, record.address, record.locality, record.providerType, *record.services]))
        if query not in text or (request.category != 'all' and record.category != request.category):
            continue
        if request.cost != 'all' and record.costStatus != request.cost:
            continue
        if request.serviceTag and request.serviceTag not in record.serviceTags:
            continue
        distance = None
        if request.origin:
            lat1, lat2 = radians(request.origin.latitude), radians(record.latitude)
            dlat = lat2 - lat1
            dlon = radians(record.longitude - request.origin.longitude)
            distance = 6371 * 2 * asin(sqrt(min(1, sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2)))
            if request.radiusKm is not None and distance > request.radiusKm:
                continue
        items.append((distance, record.model_copy(update={'distanceKm': round(distance, 2) if distance is not None else None})))
    items.sort(key=lambda pair: ((pair[0] if pair[0] is not None else 0), normalized(pair[1].name), pair[1].id))
    return DirectorySearchResponse(items=[p for _, p in items], total=len(items), directoryCounts=repository.counts(), distanceMode='approximate' if request.origin else 'none')


# Stored discovery tolerates natural request words, while /api/search keeps literal semantics.
def stored_tokens(value):
    import re
    stop = {'a','an','the','in','at','near','nearby','me','find','show','some','please','with','offering','and','of','for','to','get','need','needing'}
    aliases = {'gurgaon':'gurugram','hospitals':'hospital','centres':'center','centers':'center','centre':'center','children':'child','childrens':'child','paediatric':'pediatric','paediatrics':'pediatric','pediatrics':'pediatric'}
    return {aliases.get(word,word) for word in re.findall(r"[a-z0-9]+",normalized(value)) if word not in stop}


def reveal(repository, request, ttl_seconds=86400):
    repository.ensure_ready()
    tokens = stored_tokens(request.query)
    records=[]
    for provider in repository.all():
        if request.category != 'all' and provider.category != request.category:
            continue
        if 'hospital' in tokens and 'hospital' not in stored_tokens(provider.providerType):
            continue
        address = normalized(provider.address + ' ' + provider.locality)
        if request.area == 'Manesar' and 'manesar' not in address:
            continue
        if request.area == 'Gurugram' and not any(area in address for area in ('gurugram','gurgaon','manesar')):
            continue
        text=stored_tokens(' '.join([provider.name,provider.providerType,provider.address,provider.locality,*provider.services]))
        if tokens <= text:
            records.append(provider)
    records.sort(key=lambda p:(normalized(p.name),p.id))
    return repository.save_scope(request,records,datetime.now(timezone.utc),[],ttl_seconds,purpose='stored-v1',status='stored')
