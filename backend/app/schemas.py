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
