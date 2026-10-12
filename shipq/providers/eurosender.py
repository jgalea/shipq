import math
import uuid
from functools import cache

from .. import http
from ..models import Parcel, Place, Quote, ShipError

API = "https://www.eurosender.com/api/v2"
SERVICES = {1: "Standard", 2: "Standard Flexi", 7: "Freight", 8: "Priority Express", 11: "Priority"}


@cache
def _countries() -> dict[str, int]:
    r = http.get(f"{API}/countries", headers={"accept": "application/json"})
    if r.status_code != 200:
        raise ShipError(f"eurosender countries: HTTP {r.status_code}")
    # Islands (Madeira, Canaries, ...) share the ISO code with the mainland and carry a mainlandCountryId.
    return {c["code"]: c["id"] for c in r.json()["data"]["countries"] if c["active"] and c["mainlandCountryId"] is None}


def _address(place: Place) -> dict:
    cid = _countries().get(place.country)
    if cid is None:
        raise ShipError(f"eurosender: no service for country {place.country}")
    return {"zip": place.zip, "city": None, "street": None, "additionalInfo": None, "region": None,
            "countryId": cid, "customFields": [], "comment": None, "pudoPointCode": None}


def quotes(src: Place, dst: Place, p: Parcel) -> list[Quote]:
    body = {
        "paymentMethod": "credit_card", "selectedServiceTypeId": None, "serviceSubtype": "door_to_door",
        "accountType": "person", "additionalInsuranceId": None, "couponCode": None, "currencyCode": "EUR",
        "parcels": {"packages": [{"parcelId": str(uuid.uuid4()), "quantity": 1, "weight": p.weight,
                                  "height": math.ceil(p.height), "width": math.ceil(p.width), "length": math.ceil(p.length), "value": None}]},
        "shipment": {"pickupAddress": _address(src), "deliveryAddress": _address(dst),
                     "pickupDate": None, "addOns": [], "value": None},
        "unfinishedOrderUuid": None,
    }
    r = http.post(f"{API}/quote", json=body, headers={"accept": "application/json"})
    if r.status_code != 200:
        raise ShipError(f"eurosender: HTTP {r.status_code} {r.text[:200]}")
    out = []
    for s in r.json()["data"]["options"]["serviceTypes"]:
        start, _, end = s["serviceSubtype"].partition("_to_")
        price = s["price"]["original"]
        notes = []
        if not s["isLabelRequired"]:
            notes.append("courier brings the label")
        out.append(Quote(
            provider="eurosender",
            carrier="Eurosender",
            service=SERVICES.get(s["id"], f"service {s['id']}"),
            price=price["gross"], net=price["net"], currency=price["currencyCode"],
            days=f"{s['edt']}d",
            pickup=start == "door",
            dropoff_points=start == "shop",
            label_required=s["isLabelRequired"],
            service_id=s["serviceNameKey"],
            to_shop=end == "shop",
            url="https://www.eurosender.com/en/order",
            notes=notes,
        ))
    return out
