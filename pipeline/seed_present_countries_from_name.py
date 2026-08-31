"""One-shot fix for the residual geography gap (ROADMAP.md item 6): polities
missing `present_countries` (and often `continents`) that have no usable
Wikidata P17 chain, no direct P30 claim, and no centroid -- every signal
`pipeline/enrich_geography.py` can try has come up empty for these, but the
country is often obvious to a human reading the record's own name ("Peruvian
Republic" -> Peru). Run once; re-running is safe -- only ever fills a record
currently missing `present_countries`, and only `entity_type: polity`
records not locked via `manual_overrides: [geography]`.

Matches `canonical_name` against a conservative demonym/country-name table,
whole-word only. Two safety rules learned the hard way while building this
(see STATUS.md for the concrete examples that surfaced them):

1. Colonial/great-power adjectives (Dutch, Austrian, Italian, Portuguese,
   Belgian, Spanish, Danish, Swedish, Russian, Chinese, Japanese, American,
   Ottoman) describe a foreign power's CONTROL over a territory as often as
   they describe that power's own homeland -- "Dutch Loango-Angola" is in
   Angola, not the Netherlands; "Austrian Netherlands" is in the
   Netherlands, not Austria; "Italian Ethiopia" is in Ethiopia, not Italy;
   "Portuguese Cochin" is in India, not Portugal. If a name matches BOTH a
   colonial adjective and a different, non-colonial-adjective country, the
   colonial adjective loses. If a name matches ONLY a colonial adjective
   (no other location word in the table corroborates it), it's excluded
   entirely rather than guessed -- there's no way to tell "this record is
   about the colonial power's own home front" from "this is a foreign
   holding" without more than a name match.
2. Anything genuinely ambiguous (a name matching two distinct, non-colonial
   countries at once, e.g. "Croatia in personal union with Hungary") is
   excluded rather than guessed at.

The demonym table deliberately omits contested/multi-era ambiguous terms
entirely (Armenian, Kurdish, Macedonian, Persian, Greek, French, German,
American as standalone matches, bare "Georgia") where a historical entity's
territory is genuinely unclear or contested relative to the modern country
of the same/similar name.

Country -> continent comes from the existing sources/wikidata_country_metadata.json
cache (reverse ISO2 lookup), not a separately hardcoded table."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from pipeline.enrich_geography import field_locked

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
COUNTRY_META_PATH = ROOT / "sources" / "wikidata_country_metadata.json"

NAME_TO_COUNTRY: dict[str, str | None] = {
    "peruvian": "PE", "peru": "PE",
    "bolivian": "BO", "bolivia": "BO",
    "ecuadorian": "EC", "ecuador": "EC",
    "colombian": "CO", "colombia": "CO",
    "venezuelan": "VE", "venezuela": "VE",
    "chilean": "CL", "chile": "CL",
    "argentine": "AR", "argentina": "AR", "argentinian": "AR",
    "uruguayan": "UY", "uruguay": "UY",
    "paraguayan": "PY", "paraguay": "PY",
    "brazilian": "BR", "brazil": "BR",
    "mexican": "MX", "mexico": "MX",
    "guatemalan": "GT", "guatemala": "GT",
    "honduran": "HN", "honduras": "HN",
    "nicaraguan": "NI", "nicaragua": "NI",
    "costa rican": "CR",
    "panamanian": "PA", "panama": "PA",
    "cuban": "CU", "cuba": "CU",
    "haitian": "HT", "haiti": "HT",
    "dominican": "DO",
    "jamaican": "JM", "jamaica": "JM",
    "bashkir": "RU", "bashkiria": "RU",
    "tatarstan": "RU", "chechen": "RU", "chechnya": "RU", "dagestan": "RU",
    "yakut": "RU", "yakutia": "RU", "buryat": "RU", "buryatia": "RU",
    "kalmyk": "RU", "kalmykia": "RU", "tuvan": "RU", "tuva": "RU",
    "comorian": "KM", "comoros": "KM", "anjouan": "KM",
    "malagasy": "MG", "madagascar": "MG",
    "mauritian": "MU", "mauritius": "MU",
    "seychellois": "SC", "seychelles": "SC",
    "bhutanese": "BT", "bhutan": "BT",
    "nepali": "NP", "nepalese": "NP", "nepal": "NP",
    "sri lankan": "LK", "ceylon": "LK", "ceylonese": "LK",
    "maldivian": "MV", "maldives": "MV",
    "bangladeshi": "BD", "bangladesh": "BD",
    "burmese": "MM", "myanmar": "MM",
    "thai": "TH", "siamese": "TH", "siam": "TH",
    "cambodian": "KH", "khmer": "KH",
    "laotian": "LA", "laos": "LA",
    "vietnamese": "VN", "vietnam": "VN",
    "malaysian": "MY", "malay": "MY", "malaya": "MY",
    "singaporean": "SG", "singapore": "SG",
    "bruneian": "BN", "brunei": "BN",
    "filipino": "PH", "philippine": "PH",
    "indonesian": "ID",
    "timorese": "TL",
    "mongolian": "MN", "mongol empire": None,
    "korean": "KR", "korea": "KR",
    "japanese": "JP", "japan": "JP",
    "taiwanese": "TW", "taiwan": "TW", "formosa": "TW", "formosan": "TW",
    "afghan": "AF", "afghanistan": "AF",
    "pakistani": "PK", "pakistan": "PK",
    "bahraini": "BH", "bahrain": "BH",
    "qatari": "QA", "qatar": "QA",
    "emirati": "AE",
    "omani": "OM", "oman": "OM",
    "yemeni": "YE", "yemen": "YE",
    "saudi": "SA",
    "kuwaiti": "KW", "kuwait": "KW",
    "jordanian": "JO", "jordan": "JO", "transjordan": "JO", "transjordanian": "JO",
    "lebanese": "LB", "lebanon": "LB",
    "syrian": "SY",
    "iraqi": "IQ",
    "israeli": "IL",
    "cypriot": "CY", "cyprus": "CY",
    "turkish": "TR", "turkey": "TR", "ottoman": None,
    "georgian": "GE", "georgia": None,
    "azerbaijani": "AZ", "azeri": "AZ",
    "kazakh": "KZ", "kazakhstan": "KZ",
    "uzbek": "UZ", "uzbekistan": "UZ",
    "turkmen": "TM", "turkmenistan": "TM",
    "tajik": "TJ", "tajikistan": "TJ",
    "kyrgyz": "KG", "kyrgyzstan": "KG",
    "moldovan": "MD", "moldavian": "MD", "moldova": "MD",
    "ukrainian": "UA", "ukraine": "UA",
    "belarusian": "BY", "byelorussian": "BY", "belarus": "BY",
    "polish": "PL", "poland": "PL",
    "czech": "CZ",
    "slovak": "SK", "slovakia": "SK",
    "hungarian": "HU", "hungary": "HU",
    "romanian": "RO", "romania": "RO",
    "bulgarian": "BG", "bulgaria": "BG",
    "albanian": "AL", "albania": "AL",
    "serbian": "RS", "serbia": "RS",
    "croatian": "HR", "croatia": "HR",
    "slovenian": "SI", "slovenia": "SI",
    "bosnian": "BA", "bosnia": "BA",
    "montenegrin": "ME", "montenegro": "ME",
    "macedonian": None,
    "kosovar": "XK", "kosovo": "XK",
    "greek": None,
    "italian": "IT", "italy": "IT",
    "spanish": "ES", "spain": "ES",
    "portuguese": "PT", "portugal": "PT",
    "french": None, "france": None,
    "german": None, "germany": None,
    "austrian": "AT", "austria": "AT",
    "swiss": "CH", "switzerland": "CH",
    "belgian": "BE", "belgium": "BE",
    "dutch": "NL", "netherlands": "NL",
    "danish": "DK", "denmark": "DK",
    "norwegian": "NO", "norway": "NO",
    "swedish": "SE", "sweden": "SE",
    "finnish": "FI", "finland": "FI",
    "icelandic": "IS", "iceland": "IS",
    "irish": "IE", "ireland": "IE",
    "scottish": "GB", "welsh": "GB", "english": "GB",
    "estonian": "EE", "estonia": "EE",
    "latvian": "LV", "latvia": "LV",
    "lithuanian": "LT", "lithuania": "LT",
    "egyptian": "EG",
    "libyan": "LY", "libya": "LY",
    "tunisian": "TN", "tunisia": "TN",
    "algerian": "DZ", "algeria": "DZ",
    "moroccan": "MA", "morocco": "MA",
    "sudanese": "SD", "sudan": "SD",
    "ethiopian": "ET", "ethiopia": "ET",
    "eritrean": "ER", "eritrea": "ER",
    "somali": "SO", "somalia": "SO", "somaliland": "SO",
    "djiboutian": "DJ", "djibouti": "DJ",
    "kenyan": "KE", "kenya": "KE",
    "ugandan": "UG", "uganda": "UG",
    "tanzanian": "TZ", "tanzania": "TZ", "zanzibar": "TZ", "zanzibari": "TZ",
    "rwandan": "RW", "rwanda": "RW",
    "burundian": "BI", "burundi": "BI",
    "congolese": None,
    "gabonese": "GA", "gabon": "GA",
    "cameroonian": "CM", "cameroon": "CM",
    "nigerian": "NG", "nigeria": "NG",
    "ghanaian": "GH", "ghana": "GH", "gold coast": "GH",
    "ivorian": "CI",
    "senegalese": "SN", "senegal": "SN",
    "malian": "ML", "mali": "ML",
    "guinean": "GN", "guinea": "GN",
    "sierra leonean": "SL", "sierra leone": "SL",
    "liberian": "LR", "liberia": "LR",
    "togolese": "TG", "togo": "TG",
    "beninese": "BJ", "benin": "BJ", "dahomey": "BJ", "dahomean": "BJ",
    "nigerien": "NE", "niger": "NE",
    "chadian": "TD", "chad": "TD",
    "central african": "CF",
    "angolan": "AO", "angola": "AO",
    "mozambican": "MZ", "mozambique": "MZ",
    "zambian": "ZM", "zambia": "ZM",
    "zimbabwean": "ZW", "zimbabwe": "ZW", "rhodesian": "ZW", "rhodesia": "ZW",
    "malawian": "MW", "malawi": "MW",
    "namibian": "NA", "namibia": "NA",
    "botswanan": "BW", "botswana": "BW",
    "south african": "ZA",
    "lesotho": "LS", "basotho": "LS",
    "swazi": "SZ", "eswatini": "SZ", "swaziland": "SZ",
    "australian": "AU", "australia": "AU",
    "new zealand": "NZ",
    "fijian": "FJ", "fiji": "FJ",
    "tongan": "TO", "tonga": "TO",
    "samoan": "WS", "samoa": "WS",
    "papuan": "PG", "papua": "PG",
    "hawaiian": "US", "hawaii": "US",
    "canadian": "CA", "canada": "CA",
    "american": None,
    "cook islands": "NZ",
}

COLONIAL_ADJECTIVES = {
    "dutch", "austrian", "italian", "portuguese", "belgian", "spanish",
    "danish", "swedish", "russian", "chinese", "japanese", "american",
    "ottoman",
}

WORD_RE = {name: re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE) for name in NAME_TO_COUNTRY}


def match_country(name: str) -> str | None:
    """Return the single ISO2 country this name unambiguously matches, or
    None if there's no match, more than one distinct candidate country, or
    the only match is an unconfirmed colonial-power adjective."""
    found = [
        (pattern, iso2)
        for pattern, iso2 in NAME_TO_COUNTRY.items()
        if iso2 is not None and WORD_RE[pattern].search(name)
    ]
    distinct = {iso2 for _, iso2 in found}
    if len(distinct) > 1:
        non_colonial = [f for f in found if f[0] not in COLONIAL_ADJECTIVES]
        non_colonial_isos = {iso2 for _, iso2 in non_colonial}
        if len(non_colonial_isos) == 1:
            found, distinct = non_colonial, non_colonial_isos
    if len(distinct) == 1 and all(pattern in COLONIAL_ADJECTIVES for pattern, _ in found):
        return None
    return next(iter(distinct)) if len(distinct) == 1 else None


def load_iso2_to_continents() -> dict[str, list[str]]:
    country_meta = json.loads(COUNTRY_META_PATH.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for info in country_meta.values():
        iso2 = info.get("iso2")
        if iso2 and info.get("continents"):
            result.setdefault(iso2, set()).update(info["continents"])
    return {iso2: sorted(continents) for iso2, continents in result.items()}


def main() -> None:
    iso2_to_continents = load_iso2_to_continents()
    applied = 0
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if document.get("timeline_role") == "retired":
            continue
        if field_locked(document, "geography"):
            continue
        if document.get("entity_type", "polity") != "polity":
            continue
        geography = document.get("geography") or {}
        if geography.get("present_countries"):
            continue
        iso2 = match_country(document.get("canonical_name", ""))
        if not iso2:
            continue
        geography["present_countries"] = [iso2]
        if not geography.get("continents"):
            continents = iso2_to_continents.get(iso2)
            if continents:
                geography["continents"] = continents
        geography["confidence"] = "low"
        document["geography"] = geography
        path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
        applied += 1
    print(f"seed_present_countries_from_name: applied {applied} name-based present_countries fixes")


if __name__ == "__main__":
    main()
