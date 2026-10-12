import re
import time
from urllib.parse import quote

from .. import http
from ..models import DropPoint, Parcel, Place, Quote, ShipError

API = "https://api.packlink.com/v1"
# Packlink only runs consumer storefronts for these countries; anything else (Portugal included) is served by the Spanish one.
TENANTS = {"ES": "packlink.es", "FR": "packlink.fr", "DE": "packlink.de", "IT": "packlink.it", "NL": "packlink.nl"}


def _tenant_params(tenant: str) -> dict:
    return {"platform": "COM", "platform_country": tenant}


def normalize_zip(place: Place, tenant: str = "ES") -> Place:
    """Packlink rejects a postcode unless it's spelled exactly as in its own table ("811 01", not "81101")."""
    digits = re.sub(r"\W", "", place.zip)
    for q in dict.fromkeys([place.zip, digits[:3], digits[:2]]):
        if not q:
            continue
        r = http.get(f"{API}/locations/postalcodes/country/{place.country}", params={"q": q, **_tenant_params(tenant)})
        if r.status_code != 200:
            continue
        for row in r.json():
            if re.sub(r"\W", "", row["zipcode"]) == digits:
                return Place(place.country, row["zipcode"])
    raise ShipError(f"packlink: no postcode {place.zip} in {place.country}")


def _services(tenant: str, src: Place, dst: Place, p: Parcel) -> list[dict]:
    params = {
        **_tenant_params(tenant),
        "source": "DEFAULT",
        "from[country]": src.country, "from[zip]": src.zip,
        "to[country]": dst.country, "to[zip]": dst.zip,
        "packages[0][weight]": p.weight, "packages[0][length]": p.length,
        "packages[0][width]": p.width, "packages[0][height]": p.height,
    }
    r = http.get(f"{API}/services", params=params)
    if r.status_code != 200:
        raise ShipError(f"packlink: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def _max_dims(details: list[str]) -> list[str]:
    for d in details:
        if m := re.search(r"(\d+)-(\d+)-(\d+)\s*$", d):
            return [f"max {m[1]}×{m[2]}×{m[3]} cm"]
    return []


def quotes(src: Place, dst: Place, p: Parcel) -> list[Quote]:
    tenants = [t for t in (src.country, "ES") if t in TENANTS]
    src_n, dst_n = normalize_zip(src), normalize_zip(dst)
    rows, tenant = [], "ES"
    for tenant in dict.fromkeys(tenants):
        rows = _services(tenant, src_n, dst_n, p)
        if rows:
            break
    url = (f"https://www.{TENANTS[tenant]}/order/{src_n.country}/{quote(src_n.zip)}/{dst_n.country}/{quote(dst_n.zip)}"
           f"/service?p={p.weight:g},{p.length:g},{p.width:g},{p.height:g}")
    out = []
    for s in rows:
        price = s.get("price") or {}
        out.append(Quote(
            provider="packlink",
            carrier=s["carrier_name"],
            service=s["name"],
            price=float(price.get("total_price", s["base_price"])),
            net=float(price.get("base_price", s["base_price"])),
            currency=s.get("currency", "EUR"),
            days=str(s.get("transit_time", "")).lower().replace(" days", "d").replace(" day", "d"),
            pickup=not s.get("dropoff", False),
            dropoff_points=bool(s.get("dropoff")),
            label_required=bool(s.get("labels_required")),
            service_id=str(s["id"]),
            url=url,
            to_shop=bool(s.get("delivery_to_parcelshop")),
            notes=_max_dims(s.get("service_details", [])),
        ))
    return out


def dropoffs(service_id: str, place: Place) -> list[DropPoint]:
    z = normalize_zip(place)
    # This endpoint answers 200 with an empty list on roughly half of all calls, so an empty answer gets retried.
    for attempt in range(8):
        r = http.get(f"{API}/dropoffs/{service_id}/{z.country}/{quote(z.zip)}", params=_tenant_params("ES"))
        if r.status_code != 200:
            raise ShipError(f"packlink dropoffs: HTTP {r.status_code} {r.text[:200]}")
        if rows := r.json():
            break
        time.sleep(0.5 + attempt * 0.5)
    else:
        raise ShipError("packlink dropoffs: empty answer after 8 tries (the endpoint is intermittent, try again)")
    return [DropPoint(
        provider="packlink", carrier=d.get("carrier", ""), name=d["commerce_name"], address=d["address"],
        city=d["city"], zip=d["zip"], lat=float(d["lat"]), lon=float(d["long"]),
        hours=(d.get("opening_times") or {}).get("opening_times") or {},
    ) for d in rows]
