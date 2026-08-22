"""Geohash encode/decode — matches mobile ngeohash precision-6 cells (~1.2 km)."""

GEOHASH_PRECISION = 6
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode_geohash(latitude: float, longitude: float, precision: int = GEOHASH_PRECISION) -> str:
    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]
    bits = 0
    bit_count = 0
    even = True
    geohash: list[str] = []

    while len(geohash) < precision:
        if even:
            mid = (lng_range[0] + lng_range[1]) / 2
            if longitude >= mid:
                bits = (bits << 1) + 1
                lng_range[0] = mid
            else:
                bits <<= 1
                lng_range[1] = mid
        else:
            mid = (lat_range[0] + lat_range[1]) / 2
            if latitude >= mid:
                bits = (bits << 1) + 1
                lat_range[0] = mid
            else:
                bits <<= 1
                lat_range[1] = mid
        even = not even
        bit_count += 1
        if bit_count == 5:
            geohash.append(_BASE32[bits])
            bits = 0
            bit_count = 0

    return "".join(geohash)


def decode_geohash(geohash: str) -> dict[str, float]:
    lat_range = [-90.0, 90.0]
    lng_range = [-180.0, 180.0]
    even = True

    for char in geohash.lower():
        idx = _BASE32.index(char)
        for mask in (16, 8, 4, 2, 1):
            if even:
                mid = (lng_range[0] + lng_range[1]) / 2
                if idx & mask:
                    lng_range[0] = mid
                else:
                    lng_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if idx & mask:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            even = not even

    return {
        "latitude": (lat_range[0] + lat_range[1]) / 2,
        "longitude": (lng_range[0] + lng_range[1]) / 2,
    }
