from dataclasses import dataclass, field


class ShipError(Exception):
    pass


@dataclass
class Parcel:
    weight: float
    length: float
    width: float
    height: float

    @property
    def volumetric(self) -> float:
        return self.length * self.width * self.height / 5000

    @property
    def billable(self) -> float:
        return max(self.weight, self.volumetric)


@dataclass
class Place:
    country: str
    zip: str


@dataclass
class Quote:
    provider: str
    carrier: str
    service: str
    price: float
    net: float | None
    currency: str
    days: str
    pickup: bool
    dropoff_points: bool
    label_required: bool
    service_id: str
    url: str
    to_shop: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def collection(self) -> str:
        return "home pickup" if self.pickup else "drop-off"


@dataclass
class DropPoint:
    provider: str
    carrier: str
    name: str
    address: str
    city: str
    zip: str
    lat: float
    lon: float
    hours: dict[str, str]
    distance_m: float | None = None
