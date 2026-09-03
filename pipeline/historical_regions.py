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
    # YU (Yugoslavia's own historic ISO code, still used as present_countries
    # for its Yugoslav-era successor records) added here rather than as its
    # own bucket -- unlike SU/CS below, every YU-tagged record in this
    # dataset is genuinely Yugoslavia/a Yugoslav successor state, no
    # ambiguity (see pipeline/fix_ambiguous_country_codes.py's docstring for
    # why SU and CS were NOT added the same way).
    "balkans": ["SI", "HR", "BA", "RS", "ME", "MK", "AL", "XK", "YU"],
    "north_africa": ["EG", "LY", "TN", "DZ", "MA", "SD", "SS"],
    "horn_of_africa": ["ET", "ER", "DJ", "SO"],
    "west_africa": ["NG", "GH", "CI", "SN", "ML", "BF", "NE", "GN", "BJ", "TG",
                     "SL", "LR", "MR", "GM", "GW", "CV"],
    "central_africa": ["CD", "CG", "CM", "CF", "GA", "GQ", "TD", "AO", "ST"],
    # MG/KM/SC/MU/IO (Madagascar, Comoros, Seychelles, Mauritius, the Chagos
    # Archipelago) are Indian Ocean island nations with no dedicated bucket
    # of their own -- grouped with mainland East Africa, their closest and
    # (for IO, administratively via Mauritius) most defensible fit.
    "east_africa": ["KE", "TZ", "UG", "RW", "BI", "MW", "ZM", "MZ", "MG", "KM", "SC", "MU", "IO"],
    "southern_africa": ["ZA", "NA", "BW", "ZW", "LS", "SZ"],
    "north_america": ["US", "CA"],
    "mesoamerica": ["MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA"],
    # GY/SR (Guyana, Suriname) are geographically the Guianas, not Andean --
    # no dedicated bucket exists for them, so grouped with the Caribbean
    # (their closer cultural/colonial-history fit: CARICOM membership,
    # Anglo-/Dutch-Caribbean history) rather than the Andes.
    "caribbean": ["CU", "JM", "HT", "DO", "PR", "TT", "BS", "BB", "AW", "DM",
                  "GD", "GY", "KN", "LC", "VC", "SR"],
    "andes": ["PE", "BO", "EC", "CO", "VE"],
    "southern_cone": ["AR", "CL", "UY", "PY"],
    "brazil_amazonia": ["BR"],
    "oceania_pacific": ["AU", "NZ", "PG", "FJ", "SB", "VU", "WS", "TO", "TV",
                         "CK", "FM", "KI", "MH", "NR", "NU", "PW"],
    # AQ (Antarctica) deliberately has no bucket: the only present_countries
    # holders are 21st-century novelty micronation claims (Grand Duchy of
    # Flandrensis, Westarctica), not real historical polities -- correctly
    # left unclassified rather than forced into a made-up region.
}


def historical_region_for_country(iso_code: str) -> str | None:
    for region_id, countries in HISTORICAL_REGIONS.items():
        if iso_code in countries:
            return region_id
    return None
