"""Source admission: independently fetch allowlisted pages and verify quoted fields."""
from html.parser import HTMLParser
import re
from urllib.parse import urlparse, urljoin, unquote

import httpx
from pydantic import ValidationError

from .config import SOURCE_DOMAINS
from .schemas import Candidate, Citation, DiscoveryProvider


def text_normalize(value):
    return ' '.join(str(value).casefold().split())


def allowed_url(url, domains):
    parsed = urlparse(str(url))
    host = parsed.hostname or ''
    return (parsed.scheme == 'https' and not parsed.username and not parsed.password
            and parsed.port in (None, 443)
            and any(host == d or host.endswith('.' + d) for d in domains))


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = None
        self.json_script = False
    def handle_data(self, data):
        if self.hidden == 'style':
            return
        if self.hidden == 'script' and not self.json_script:
            if re.search(r'(?:latitude|longitude|lat|lng)\s*[=:]\s*-?\d+\.\d+', data, re.I):
                self.parts.append(data[:10000])
            return
        self.parts.append(data)
    def handle_endtag(self, tag):
        if tag == self.hidden:
            self.hidden = None
            self.json_script = False
    def handle_starttag(self, tag, attrs):
        if tag in ('style', 'script'):
            self.hidden = tag
            self.json_script = dict(attrs).get('type', '').lower() in ('application/ld+json', 'application/json')
        # Provider-published map/contact hrefs and embedded JSON can carry evidence.
        self.parts.extend(value for key, value in attrs if (key in ('href', 'content') or (tag == 'iframe' and key == 'src')) and value)


def location_evidence(page):
    """Extract actual local place/geo pairs from published links and JSON-LD."""
    found, seen = [], set()
    def add(latitude, longitude, quote):
        lat, lon = float(latitude), float(longitude)
        if 28.2 <= lat <= 28.7 and 76.6 <= lon <= 77.3 and (lat, lon) not in seen:
            seen.add((lat, lon))
            found.append({'latitude': lat, 'longitude': lon, 'quote': quote})
    number = r'(-?\d+\.\d+)'
    for match in re.finditer(r'https://[^\s<>"\x27]+', page):
        link = unquote(match.group(0))
        host = urlparse(link).hostname or ''
        if host not in ('www.google.com', 'google.com', 'maps.google.com') or '/maps' not in link:
            continue
        pair = re.search(r'!3d' + number + r'!4d' + number, link)
        if pair:
            add(pair[1], pair[2], match[0])
            continue
        pair = re.search(r'!2m2!1d' + number + r'!2d' + number, link)
        if pair:
            add(pair[2], pair[1], match[0])
            continue
        pair = re.search(r'[?&](?:q|query)=' + number + ',' + number, link)
        if pair:
            add(pair[1], pair[2], match[0])
            continue
        lat = re.search(r'[?&](?:lat|latitude)=' + number, link)
        lon = re.search(r'[?&](?:lng|lon|longitude)=' + number, link)
        if lat and lon:
            add(lat[1], lon[1], match[0])
    for first, second in [('latitude', 'longitude'), ('longitude', 'latitude')]:
        pattern = r'["\x27]' + first + r'["\x27]\s*:\s*["\x27]?' + number + r'["\x27]?\s*,\s*["\x27]' + second + r'["\x27]\s*:\s*["\x27]?' + number
        for match in re.finditer(pattern, page):
            add(match[1] if first == 'latitude' else match[2], match[2] if first == 'latitude' else match[1], match[0])
    for match in re.finditer(r'(?:map coordinates|coordinates)\s*:?\s*' + number + r'\s*,\s*' + number, page, re.I):
        add(match[1], match[2], match[0])
    return found


class SourceFetcher:
    def __init__(self, domains=SOURCE_DOMAINS, transport=None):
        self.domains, self.transport = domains, transport

    async def __call__(self, url):
        current = str(url)
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, transport=self.transport) as client:
            for hop in range(4):
                if not allowed_url(current, self.domains):
                    raise ValueError('Unapproved evidence source or redirect')
                async with client.stream('GET', current, headers={'User-Agent': 'CareLearnEvidence/0.1'}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        target = response.headers.get('location')
                        if not target or hop == 3:
                            raise ValueError('Evidence redirect limit exceeded')
                        current = urljoin(current, target)
                        # Validate before requesting the next destination, including HTTPS and port.
                        if not allowed_url(current, self.domains):
                            raise ValueError('Unapproved evidence source or redirect')
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get('content-type', '')
                    if not any(kind in content_type for kind in ('text/', 'application/json', 'application/ld+json')):
                        raise ValueError('Unsupported evidence content')
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise ValueError('Evidence page exceeds limit')
                        chunks.append(chunk)
                parser = PageText()
                parser.feed(b''.join(chunks).decode('utf-8', errors='replace'))
                return ' '.join(parser.parts)
        raise ValueError('Evidence redirect limit exceeded')


class EvidenceValidator:
    def __init__(self, fetch_source=None, allowed_domains=SOURCE_DOMAINS):
        self.domains = allowed_domains
        self.fetch_source = fetch_source or SourceFetcher(allowed_domains)
        self.last_rejections = []

    async def validate(self, candidates, now):
        accepted, warnings, pages = [], [], {}
        self.last_rejections = []
        for raw in candidates:
            try:
                record = Candidate.model_validate(raw)
                if not all(str(getattr(record, field)).strip() for field in ('name', 'providerType', 'address', 'locality', 'coordinateStatus')):
                    raise ValueError('Incomplete identity')
                if not record.citations or not record.relevanceReason or not record.services:
                    raise ValueError('Missing source-backed fields')
                evidence = {}
                verified_citations = []
                for citation in record.citations:
                    url = str(citation.url)
                    if not allowed_url(url, self.domains):
                        raise ValueError('Unapproved citation URL')
                    if url not in pages:
                        pages[url] = await self.fetch_source(url)
                    quote = text_normalize(citation.quote)
                    if quote not in text_normalize(pages[url]):
                        raise ValueError('Quote absent from source')
                    for field in citation.fields:
                        evidence.setdefault(field, []).append((url, quote))
                    verified_citations.append(Citation(**citation.model_dump(exclude={'quote'})))
                urls = {str(c.url) for c in record.citations}
                if str(record.sourceUrl) not in urls or str(record.coordinateSourceUrl) not in urls:
                    raise ValueError('Provider/coordinate citation missing')

                def supported(field, value, required_url=None):
                    values = value if isinstance(value, list) else [value]
                    return all(any((required_url is None or url == required_url) and text_normalize(part) in quote for url, quote in evidence.get(field, [])) for part in values)

                original_services = record.services
                record.services = list(dict.fromkeys(service for service in record.services if supported('services', service)))
                if not record.services:
                    raise ValueError('No source-backed services')
                if record.services != original_services:
                    warnings.append('Unsupported service descriptions were omitted.')
                for field in ('name', 'providerType', 'address', 'locality', 'services', 'relevanceReason'):
                    if not supported(field, getattr(record, field)):
                        raise ValueError('Unsupported core field: ' + field)
                # Both numeric coordinates must appear in the cited location evidence, not model memory.
                for field in ('latitude', 'longitude'):
                    value = getattr(record, field)
                    matched = any(url == str(record.coordinateSourceUrl) and any(abs(float(token) - value) < 1e-7 for token in re.findall(r'-?\d+\.\d+', quote)) for url, quote in evidence.get(field, []))
                    if not matched:
                        raise ValueError('Untraceable coordinate')
                paired = any(url == str(record.coordinateSourceUrl) and any(abs(float(token)-record.latitude) < 1e-7 for token in re.findall(r'-?\d+\.\d+', quote)) and any(abs(float(token)-record.longitude) < 1e-7 for token in re.findall(r'-?\d+\.\d+', quote)) for url, quote in evidence.get('latitude', []) if (url, quote) in evidence.get('longitude', []))
                if not paired:
                    raise ValueError('Latitude/longitude are not paired in source evidence')
                label = text_normalize(record.providerType)
                if record.category == 'health' and not any(v in label for v in ('hospital', 'clinic', 'health')):
                    raise ValueError('Unsupported category')
                if record.category == 'learning' and not any(v in label for v in ('learning', 'school', 'education', 'training', 'it centre', 'it center')):
                    raise ValueError('Unsupported category')
                omitted = False
                for field in ('feeNotes', 'phone', 'website', 'hours', 'languages', 'ageRange'):
                    value = getattr(record, field)
                    if value is not None and not supported(field, value):
                        setattr(record, field, None)
                        omitted = True
                if record.costStatus != 'unknown' and not supported('costStatus', record.costStatus):
                    record.costStatus = 'unknown'
                    omitted = True
                tags = [tag for tag in record.serviceTags if tag == 'vaccination' and supported('serviceTags', tag)]
                omitted |= tags != record.serviceTags
                record.serviceTags = tags
                # AI discoveries cannot certify WhatsApp support; preserve verified cache evidence separately.
                if record.whatsappNumber or record.whatsappConfirmed:
                    omitted = True
                record.whatsappNumber = None
                record.whatsappConfirmed = False
                record.whatsappSourceUrl = None
                record.whatsappCheckedAt = None
                record.checkedAt = now.date()
                record.retrievedAt = now
                # Coordinate precision and relevance are conservative even when source text is more confident.
                record.coordinateStatus = 'Source-backed approximate location; confirm the entrance with the provider'
                record.distanceKm = None
                public = record.model_dump(exclude={'citations'})
                public['citations'] = verified_citations
                accepted.append(DiscoveryProvider.model_validate(public))
                if omitted:
                    warnings.append('Unsupported optional provider information was left unconfirmed.')
            except (ValidationError, ValueError, httpx.HTTPError, OSError) as error:
                reason = 'invalid_schema' if isinstance(error, ValidationError) else 'source_fetch_failed' if isinstance(error, (httpx.HTTPError, OSError)) else str(error)
                self.last_rejections.append(reason)
                warnings.append('A provider with incomplete or unverifiable source/location evidence was omitted.')
        return accepted, list(dict.fromkeys(warnings))
