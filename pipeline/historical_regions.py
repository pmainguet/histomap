"""Curated ISO alpha-2 country -> historical region lookup. A starter set,
not exhaustive -- a country missing from this table falls back to nothing
(left unclassified) in derive_historical_regions.py, never guessed via
continent, same "cheap default, grow the table later" pattern as every
other reference list in this project. Region ids are not Period.tier
citizens (see ONTOLOGY.md's "Tree, lanes, graph" section) -- this is a
standalone spatial classification, referenced by geography.
"""

from __future__ import annotations

HISTORICAL_REGIONS: dict[str, list[str]] = {
    "west_asia": ["IR", "IQ", "TR", "SY", "JO", "LB", "IL", "PS", "SA", "YE",
                  "OM", "AE", "QA", "BH", "KW", "CY", "GE", "AM", "AZ"],
    "central_asia": ["KZ", "UZ", "TM", "TJ", "KG", "AF"],
    "south_asia": ["IN", "PK", "BD", "LK", "NP", "BT", "MV"],
    "east_asia": ["CN", "JP", "KR", "KP", "MN", "TW", "HK", "MO"],
    "southeast_asia": ["ID", "MY", "TH", "VN", "PH", "MM", "KH", "LA", "SG", "BN", "TL"],
    "western_europe": ["FR", "DE", "BE", "NL", "LU", "GB", "IE", "CH", "AT", "MC", "LI"],
    "northern_europe": ["SE", "NO", "DK", "FI", "IS", "EE", "LV", "LT"],
    "southern_europe": ["IT", "ES", "PT", "GR", "MT", "SM", "VA", "AD"],
    "eastern_europe": ["RU", "UA", "BY", "PL", "CZ", "SK", "HU", "RO", "BG", "MD"],
    "balkans": ["SI", "HR", "BA", "RS", "ME", "MK", "AL", "XK"],
    "north_africa": ["EG", "LY", "TN", "DZ", "MA", "SD", "SS"],
    "horn_of_africa": ["ET", "ER", "DJ", "SO"],
    "west_africa": ["NG", "GH", "CI", "SN", "ML", "BF", "NE", "GN", "BJ", "TG",
                     "SL", "LR", "MR", "GM", "GW", "CV"],
    "central_africa": ["CD", "CG", "CM", "CF", "GA", "GQ", "TD", "AO", "ST"],
    "east_africa": ["KE", "TZ", "UG", "RW", "BI", "MW", "ZM", "MZ"],
    "southern_africa": ["ZA", "NA", "BW", "ZW", "LS", "SZ"],
    "north_america": ["US", "CA"],
    "mesoamerica": ["MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA"],
    "caribbean": ["CU", "JM", "HT", "DO", "PR", "TT", "BS", "BB"],
    "andes": ["PE", "BO", "EC", "CO"],
    "southern_cone": ["AR", "CL", "UY", "PY"],
    "brazil_amazonia": ["BR"],
    "oceania_pacific": ["AU", "NZ", "PG", "FJ", "SB", "VU", "WS", "TO"],
}


def historical_region_for_country(iso_code: str) -> str | None:
    for region_id, countries in HISTORICAL_REGIONS.items():
        if iso_code in countries:
            return region_id
    return None
