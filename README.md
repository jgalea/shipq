<div align="center">

# shipq

[![License](https://img.shields.io/badge/LICENSE-MIT-5C9E31?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/PYTHON-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org)
[![Built by](https://img.shields.io/badge/BUILT%20BY-JGALEA-8A2BE2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/jgalea)

**Compare parcel shipping quotes across courier aggregators from the terminal.**

</div>

One parcel, every service Packlink and Eurosender sell for that route, cheapest first, with VAT. Each row says whether the courier collects from your door or you drop it off, and `--near` finds the closest drop-off point for each drop-off service.

```
uv tool install git+https://github.com/jgalea/shipq

shipq quote PT:1100-148 SK:81101 -w 4.7 -s 60x30x20
shipq quote PT:1100-148 SK:81101 -w 4.7 -s 60x30x20 --pickup            # door collection only
shipq quote PT:1100-148 SK:81101 -w 4.7 -s 60x30x20 --near 38.71,-9.14 --radius 100
shipq quote ES:08001 DE:10115 -w 2 -s 30x20x10 --json
shipq points 22363 PT:1100-148 --near "Praça do Comércio, Lisboa"       # Packlink service id from --json
```

Carriers bill the higher of the real weight and the volumetric weight (L×W×H in cm / 5000), so the box size matters as much as the weight. The table title says when the volumetric weight wins.

Both providers' public quote endpoints are used as their own websites use them, with no account. Packlink only runs storefronts for ES, FR, DE, IT and NL, and quotes from other origins (Portugal included) come from the Spanish one. Its drop-off point endpoint returns an empty list about half the time, so empty answers are retried. Eurosender doesn't expose drop-off point lists before an order is started, so its drop-off services show without a distance.

`--near` takes `lat,lon`, or an address looked up on OpenStreetMap's Nominatim.

Not affiliated with Packlink or Eurosender.
