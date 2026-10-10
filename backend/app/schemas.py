"""Public data and request/response contracts shared by future directory services."""
from datetime import date
from typing import Annotated, Literal, Self
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator

Latitude = Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=-180, le=180, allow_inf_nan=False)]
ProviderId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]
Query = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Origin(Contract):
    latitude: Latitude
    longitude: Longitude


class SearchRequest(Contract):
    query: Query = ""
    category: Literal["all", "health", "learning"] = "all"
    cost: Literal["all", "free", "paid", "unknown"] = "all"
    serviceTag: Literal["vaccination"] | None = None
    origin: Origin | None = None
    radiusKm: Annotated[float, Field(ge=1, le=50, allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def radius_requires_origin(self) -> Self:
        if self.radiusKm is not None and self.origin is None:
            raise ValueError("radiusKm requires origin")
        return self


class Provider(Contract):
    id: ProviderId
    name: str
    providerType: str
    category: Literal["health", "learning"]
    address: str
    locality: str
    latitude: Latitude
    longitude: Longitude
    services: list[str]
    serviceTags: list[str]
    costStatus: Literal["free", "paid", "unknown"]
    feeNotes: str | None = None
    phone: str | None = None
    website: HttpUrl | None = None
    hours: str | None = None
    languages: list[str] | None = None
    ageRange: str | None = None
    sourceUrl: HttpUrl
    checkedAt: date
    coordinateStatus: str
    coordinateSourceUrl: HttpUrl
    whatsappNumber: str | None = None
    whatsappConfirmed: bool = False
    whatsappSourceUrl: HttpUrl | None = None
    whatsappCheckedAt: date | None = None
    distanceKm: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None


class DirectoryCounts(Contract):
    health: Annotated[int, Field(ge=0)]
    learning: Annotated[int, Field(ge=0)]


class SearchResponse(Contract):
    items: list[Provider]
    total: Annotated[int, Field(ge=0)]
    directoryCounts: DirectoryCounts
    distanceMode: Literal["none", "approximate"] = "none"
    coverage: Literal["Gurugram curated directory"] = "Gurugram curated directory"


class InquiryRequest(Contract):
    context: Literal["general", "vaccination"] = "general"


class InquiryResponse(Contract):
    centerId: ProviderId
    recipientName: str
    message: str
    mode: Literal["whatsapp", "preview"]
    whatsappUrl: HttpUrl | None = None
    reason: str | None = None


class HealthResponse(Contract):
    status: Literal["ok"] = "ok"
    database: Literal["ready"] = "ready"


class ErrorDetail(Contract):
    code: str
    message: str


class ErrorResponse(Contract):
    error: ErrorDetail


# Phase 9 adds discovery contracts without changing the Phase 8 directory defaults.
from datetime import datetime


class Citation(Contract):
    url: HttpUrl
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    fields: list[str]


class EvidenceCitation(Citation):
    # Quotes exist only in transient extraction/validation, not public responses or SQLite.
    quote: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class DiscoveryProvider(Provider):
    citations: list[Citation] = Field(default_factory=list)
    retrievedAt: datetime | None = None
    relevanceReason: Annotated[str, StringConstraints(max_length=300)] | None = None


class Candidate(DiscoveryProvider):
    citations: list[EvidenceCitation]


class Extraction(Contract):
    providers: list[Candidate]


class DiscoverRequest(Contract):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    category: Literal['all', 'health', 'learning'] = 'all'
    area: Literal['Gurugram', 'Manesar'] = 'Gurugram'
    refresh: bool = False
    savedScopeId: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')] | None = None


class DiscoveryResponse(Contract):
    items: list[DiscoveryProvider]
    total: Annotated[int, Field(ge=0)]
    directoryCounts: DirectoryCounts
    distanceMode: Literal['none'] = 'none'
    coverage: Literal['Gurugram source-backed discovery'] = 'Gurugram source-backed discovery'
    scopeId: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')]
    retrievedAt: datetime
    retrievalStatus: Literal['fresh', 'cached', 'stored']
    warnings: list[str] = Field(default_factory=list)


class ScopedSearchRequest(SearchRequest):
    scopeId: Annotated[str, StringConstraints(pattern=r'^[a-f0-9]{64}$')] | None = None


class DirectorySearchResponse(SearchResponse):
    items: list[DiscoveryProvider]
    coverage: Literal['Gurugram source-backed discovery'] = 'Gurugram source-backed discovery'


class StoredSearchRequest(Contract):
    query: Query = ''
    category: Literal['all','health','learning'] = 'all'
    area: Literal['Gurugram','Manesar'] = 'Gurugram'
