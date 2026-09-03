"""One-off pass for ROADMAP.md's geography-gaps item: infer a still-missing
`continents` value from a documented Wikidata relationship neighbor's own
continents, when every signal `enrich_geography.py` builds (P17 chain,
direct P30, centroid) has already come up empty for a record.

`sources/wikidata_relationships.json` already carries P361 (part of), P527
(has part), P155 (follows), P156 (followed by), P1365 (replaces), and P1366
(replaced by) links -- fetched by `pipeline/enrich_relationships.py` for an
unrelated purpose (consolidation-review candidate pooling) and never
consulted for geography. These relationship kinds are, structurally,
almost always continent-stable: a state's documented predecessor,
successor, part-of container, or constituent part essentially never sits on
a different continent. When a gap record's relationship neighbors that
DO have a known continent all agree on exactly one, that's real, if
indirect, evidence -- confidence "low", same tier as every other inferred
(non-asserted) geography signal in this pipeline.

Deliberately conservative: a record with disagreeing neighbors, or none
with known continents, is left alone rather than guessed. `--apply` writes;
without it, `main()` only prints the proposal list grouped by continent for
review, the same "dry-run first, review by hand" discipline
`seed_present_countries_from_name.py` used (see STATUS.md for the false
positives that discipline caught there) -- and it caught one here too:
spot-checking every relationship property's agreement rate against
already-resolved records found P361/P527 (real containment) agree
~92-97%, P155/P156/P1365/P1366 (succession) ~98%, but a single bad
succession link is a real, demonstrated failure mode (County of Edessa
<-P1365/P1366-> the Fatimid Caliphate, a spurious Wikidata claim -- Edessa
was never the Fatimids' successor). `is_safe()` excludes a proposal
resting on exactly one succession-only link from the default `--apply`;
`--include-risky` overrides that.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from pipeline.enrich_geography import field_locked

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
RELATIONSHIP_CACHE = ROOT / "sources" / "wikidata_relationships.json"

RELATIONSHIP_PROPERTIES = ("P361", "P527", "P155", "P156", "P1365", "P1366")


def build_qid_to_continents() -> dict[str, list[str]]:
    """QID -> continents, from every currently-resolved polity that carries
    a Wikidata QID and a non-empty `continents`. This is the "evidence
    pool" a gap record's relationship neighbors are checked against."""
    mapping: dict[str, set[str]] = {}
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        qid = (document.get("external_ids") or {}).get("wikidata")
        continents = (document.get("geography") or {}).get("continents") or []
        if qid and continents:
            mapping.setdefault(qid, set()).update(continents)
    return {qid: sorted(continents) for qid, continents in mapping.items()}


def neighbor_qids(qid: str, relationships: list[dict]) -> dict[str, set[str]]:
    """Every QID linked to `qid` by one of RELATIONSHIP_PROPERTIES, in
    either direction (a gap record can appear as either the source or the
    target of a documented link -- see enrich_relationships.py's fetch),
    mapped to which propert(y/ies) provided that link. The property is kept
    (not just the neighbor set) so a caller can weigh evidence quality --
    spot-checking against already-resolved records found P361/P527 (real
    containment) agree with the entity's own continent ~92-97% of the time,
    P155/P156/P1365/P1366 (succession) ~98%, but a single bad succession
    link is still a real failure mode (found live, 3 September 2026: County
    of Edessa <-P1365/P1366-> the Fatimid Caliphate, a spurious Wikidata
    claim -- Edessa was never the Fatimids' successor)."""
    neighbors: dict[str, set[str]] = {}
    for link in relationships:
        property_ = link.get("property")
        if property_ not in RELATIONSHIP_PROPERTIES:
            continue
        if link.get("source") == qid:
            neighbors.setdefault(link["target"], set()).add(property_)
        elif link.get("target") == qid:
            neighbors.setdefault(link["source"], set()).add(property_)
    return neighbors


CONTAINMENT_PROPERTIES = {"P361", "P527"}  # part of / has part -- structurally geographic


def propose_continents() -> list[dict]:
    """One proposal per gap polity where exactly one continent is
    unambiguously implied by its documented relationship neighbors. Each
    proposal also carries `neighbor_count` and `has_containment_evidence`
    (True if at least one contributing link is P361/P527) so a caller can
    apply its own evidence-strength bar before writing anything -- this
    function itself stays a plain, complete proposal list."""
    relationships = (
        json.loads(RELATIONSHIP_CACHE.read_text(encoding="utf-8"))
        if RELATIONSHIP_CACHE.exists() else []
    )
    qid_to_continents = build_qid_to_continents()
    proposals = []
    for path in sorted(POLITIES_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        if field_locked(document, "geography"):
            continue
        if (document.get("geography") or {}).get("continents"):
            continue
        qid = (document.get("external_ids") or {}).get("wikidata")
        if not qid:
            continue
        implied_continents: set[str] = set()
        evidence: dict[str, set[str]] = {}
        for neighbor_qid, properties in neighbor_qids(qid, relationships).items():
            continents = qid_to_continents.get(neighbor_qid)
            if continents:
                implied_continents.update(continents)
                evidence[neighbor_qid] = properties
        if len(implied_continents) != 1:
            continue
        proposals.append(
            {
                "id": document["id"],
                "canonical_name": document.get("canonical_name", document["id"]),
                "qid": qid,
                "continent": next(iter(implied_continents)),
                "neighbor_qids": sorted(evidence),
                "neighbor_count": len(evidence),
                "has_containment_evidence": any(
                    properties & CONTAINMENT_PROPERTIES for properties in evidence.values()
                ),
            }
        )
    return proposals


def apply_proposals(proposals: list[dict]) -> int:
    applied = 0
    for proposal in proposals:
        path = POLITIES_DIR / f"{proposal['id']}.yaml"
        if not path.exists():
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        geography = document.get("geography") or {}
        if geography.get("continents"):
            continue
        geography["continents"] = [proposal["continent"]]
        geography.setdefault("confidence", "low")
        document["geography"] = geography
        path.write_text(
            yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
        applied += 1
    return applied


def is_safe(proposal: dict) -> bool:
    """Default evidence-strength bar: cross-corroborated by 2+ independent
    neighbors (each disagreement would already have excluded the proposal,
    so multiple neighbors surviving that filter is strong agreement), OR at
    least one P361/P527 (structurally geographic) link even alone. Excludes
    a proposal resting on a SINGLE succession-only (P155/P156/P1365/P1366)
    link -- the one demonstrated failure mode found live, 3 September 2026
    (County of Edessa <-P1365/P1366-> the Fatimid Caliphate, a spurious
    Wikidata claim), even though succession links agree ~98% of the time in
    aggregate; a lone link carries no cross-check at all. `--include-risky`
    applies those anyway."""
    return proposal["neighbor_count"] > 1 or proposal["has_containment_evidence"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the inferred continents. Without this flag, only prints the proposal list.",
    )
    parser.add_argument(
        "--include-risky", action="store_true",
        help="Also apply proposals rest on a single succession-only (P155/P156/P1365/P1366) "
        "link -- see is_safe()'s docstring for why these are excluded by default.",
    )
    args = parser.parse_args()

    proposals = propose_continents()
    to_apply = proposals if args.include_risky else [p for p in proposals if is_safe(p)]
    by_continent: dict[str, list[dict]] = {}
    for proposal in proposals:
        by_continent.setdefault(proposal["continent"], []).append(proposal)
    for continent, group in sorted(by_continent.items()):
        print(f"\n{continent} ({len(group)}):")
        for proposal in group:
            flag = "" if is_safe(proposal) else "  [single succession link -- excluded by default]"
            print(f"  {proposal['id']} | {proposal['canonical_name']} | via {proposal['neighbor_qids']}{flag}")
    print(f"\n{len(proposals)} proposals total, {len(to_apply)} pass the default safety bar.")

    if args.apply:
        applied = apply_proposals(to_apply)
        print(f"applied: {applied}")
    else:
        print("Dry run -- re-run with --apply to write these.")


if __name__ == "__main__":
    main()
