"""Reconcile normalized Seshat polities with canonical Histomap records."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import yaml
from rapidfuzz import fuzz, process
from unidecode import unidecode

ROOT = Path(__file__).resolve().parent.parent
POLITIES_DIR = ROOT / "polities"
SESHAT_PATH = ROOT / "sources" / "seshat_polities.parquet"
CROSSWALK_PATH = ROOT / "sources" / "seshat_crosswalk.parquet"
REVIEW_PATH = ROOT / "reports" / "seshat_reconciliation.jsonl"
SUMMARY_PATH = ROOT / "reports" / "reconcile_summary.md"
UNMATCHED_PATH = ROOT / "reports" / "seshat_unmatched_drafts.yaml"
DECISIONS_PATH = ROOT / "reports" / "seshat_review_decisions.jsonl"

PHASE_WORDS = {"early", "middle", "mid", "late", "old", "new", "first", "second", "third"}
TYPE_WORDS = {
    "caliphate",
    "confederacy",
    "dynasty",
    "empire",
    "kingdom",
    "principality",
    "republic",
    "sultanate",
    "state",
}
NOISE_WORDS = {"the", "of", "and"}
REGION_CONTINENTS = {
    "africa": {"africa"},
    "east asia": {"asia"},
    "south asia": {"asia"},
    "southeast asia": {"asia"},
    "southwest asia": {"asia"},
    "central asia": {"asia"},
    "europe": {"europe"},
    "north america": {"north_america"},
    "south america": {"south_america"},
    "oceania": {"oceania"},
}


@dataclass(frozen=True)
class CandidateScore:
    polity_id: str
    canonical_name: str
    name_score: float
    primary_name_score: float
    date_score: float
    geography_score: float
    type_score: float
    total_score: float


def normalize_name(value: str, strip_types: bool = False) -> str:
    text = unidecode(value).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\s+-\s+.*$", " ", text)
    words = re.findall(r"[a-z0-9]+", text)
    ignored = NOISE_WORDS | PHASE_WORDS | (TYPE_WORDS if strip_types else set())
    return " ".join(word for word in words if word not in ignored)


def date_compatibility(left_start: int, left_end: int, right_start: int, right_end: int | None) -> float:
    right_end = 2026 if right_end is None else right_end
    intersection = max(0, min(left_end, right_end) - max(left_start, right_start) + 1)
    if not intersection:
        return 0.0
    union = max(left_end, right_end) - min(left_start, right_start) + 1
    shorter = min(left_end - left_start + 1, right_end - right_start + 1)
    return max(intersection / union, intersection / shorter)


def _names(document: dict) -> list[str]:
    values = [document["canonical_name"]]
    for key, value in (document.get("names") or {}).items():
        if key == "aliases_en":
            values.extend(part.strip() for part in str(value).split("|") if part.strip())
        elif value:
            values.append(str(value))
    return values


def score_candidate(seshat: dict, document: dict) -> CandidateScore:
    seshat_names = {
        normalize_name(str(seshat["canonical_name"])),
        normalize_name(str(seshat["canonical_name"]), strip_types=True),
    }
    canonical_names = {
        normalized
        for name in _names(document)
        for normalized in (normalize_name(name), normalize_name(name, strip_types=True))
        if normalized
    }
    primary_names = {
        normalized
        for normalized in (
            normalize_name(document["canonical_name"]),
            normalize_name(document["canonical_name"], strip_types=True),
        )
        if normalized
    }

    def best_name_score(right_names: set[str]) -> float:
        best = 0.0
        for left in seshat_names:
            for right in right_names:
                if not left or not right:
                    continue
                pair_score = float(fuzz.WRatio(left, right))
                shared_tokens = set(left.split()) & set(right.split())
                whole_name_score = fuzz.ratio(left, right)
                if not shared_tokens and whole_name_score < 80:
                    pair_score = min(pair_score, 75.0)
                union_tokens = set(left.split()) | set(right.split())
                token_jaccard = len(shared_tokens) / len(union_tokens) if union_tokens else 0
                if left != right and token_jaccard < 0.6 and whole_name_score < 85:
                    pair_score = min(pair_score, 85.0)
                best = max(best, pair_score)
        return best

    name_score = best_name_score(canonical_names)
    primary_name_score = best_name_score(primary_names)
    date_score = 100 * date_compatibility(
        int(seshat["start_year"]),
        int(seshat["end_year"]),
        int(document["start"]),
        document.get("end"),
    )
    expected_continents = REGION_CONTINENTS.get(str(seshat.get("world_region", "")).lower(), set())
    actual_continents = set((document.get("geography") or {}).get("continents", []))
    geography_score = 100.0 if expected_continents & actual_continents else 50.0 if not actual_continents else 0.0
    seshat_types = set(normalize_name(str(seshat["canonical_name"])).split()) & TYPE_WORDS
    canonical_types = set(normalize_name(document["canonical_name"]).split()) & TYPE_WORDS
    type_score = 100.0 if seshat_types and seshat_types & canonical_types else 50.0 if not seshat_types else 0.0
    total = 0.55 * name_score + 0.30 * date_score + 0.10 * geography_score + 0.05 * type_score
    return CandidateScore(
        polity_id=document["id"],
        canonical_name=document["canonical_name"],
        name_score=round(name_score, 2),
        primary_name_score=round(primary_name_score, 2),
        date_score=round(date_score, 2),
        geography_score=round(geography_score, 2),
        type_score=round(type_score, 2),
        total_score=round(total, 2),
    )


def decide(scores: list[CandidateScore], eligibility: dict[str, str]) -> tuple[str, CandidateScore | None]:
    if not scores:
        return "unmatched", None
    best = scores[0]
    runner_up = scores[1].total_score if len(scores) > 1 else 0
    margin = best.total_score - runner_up
    if (
        eligibility.get(best.polity_id) == "accepted"
        and best.total_score >= 82
        and best.name_score >= 88
        and best.primary_name_score >= 88
        and best.date_score >= 65
        and margin >= 6
    ):
        return "auto", best
    if best.total_score >= 55 and best.name_score >= 60:
        return "review", best
    return "unmatched", best


def load_review_decisions(path: Path = DECISIONS_PATH) -> dict[str, dict]:
    if not path.exists():
        return {}
    decisions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            decision = json.loads(line)
            decisions[decision["seshat_id"]] = decision
    return decisions


def _load_documents() -> tuple[dict[str, tuple[Path, dict]], dict[str, list[str]]]:
    documents = {}
    name_index: dict[str, list[str]] = defaultdict(list)
    for path in POLITIES_DIR.glob("*.yaml"):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        documents[document["id"]] = (path, document)
        if document.get("eligibility") == "excluded":
            continue
        if str(document.get("canonical_name", "")).strip().lower() in {"", "nan", "none"}:
            continue
        for name in _names(document):
            for normalized in {normalize_name(name), normalize_name(name, strip_types=True)}:
                if normalized:
                    name_index[normalized].append(document["id"])
    return documents, name_index


def run(apply: bool = True) -> dict[str, int]:
    documents, name_index = _load_documents()
    seshat = pd.read_parquet(SESHAT_PATH)
    choices = list(name_index)
    eligibility = {polity_id: document.get("eligibility", "review") for polity_id, (_, document) in documents.items()}
    results = []
    crosswalk = []
    unmatched_drafts = []
    matches_by_polity: dict[str, list[str]] = defaultdict(list)
    manual_decisions = load_review_decisions()

    for row in seshat.to_dict(orient="records"):
        query_names = {
            normalize_name(str(row["canonical_name"])),
            normalize_name(str(row["canonical_name"]), strip_types=True),
        }
        candidate_ids: set[str] = set()
        for query in query_names:
            for matched_name, _, _ in process.extract(query, choices, scorer=fuzz.WRatio, limit=20):
                candidate_ids.update(name_index[matched_name])
        raw_scores = sorted(
            (score_candidate(row, documents[polity_id][1]) for polity_id in candidate_ids),
            key=lambda score: (-score.total_score, -score.name_score, score.polity_id),
        )
        scores = []
        seen_canonical_names: set[str] = set()
        for score in raw_scores:
            canonical_key = normalize_name(score.canonical_name)
            if canonical_key in seen_canonical_names:
                continue
            seen_canonical_names.add(canonical_key)
            scores.append(score)
            if len(scores) == 5:
                break
        decision, best = decide(scores, eligibility)
        manual = manual_decisions.get(str(row["seshat_id"]))
        if manual and manual.get("decision") == "accept":
            polity_id = manual.get("polity_id")
            if polity_id not in documents:
                raise ValueError(f"review decision references unknown polity {polity_id}")
            best = next((score for score in scores if score.polity_id == polity_id), None)
            if best is None:
                best = score_candidate(row, documents[polity_id][1])
            decision = "manual"
        elif manual and manual.get("decision") == "reject":
            decision = "rejected"
        result = {
            "seshat_id": row["seshat_id"],
            "seshat_name": row["canonical_name"],
            "start_year": int(row["start_year"]),
            "end_year": int(row["end_year"]),
            "peak_population_log10": row.get("peak_population_log10"),
            "peak_area_km2_log10": row.get("peak_area_km2_log10"),
            "peak_social_complexity": row.get("peak_social_complexity"),
            "decision": decision,
            "best_polity_id": best.polity_id if best else None,
            "candidates": [asdict(score) for score in scores],
        }
        results.append(result)
        crosswalk.append(
            {
                "seshat_id": row["seshat_id"],
                "polity_id": best.polity_id if best and decision in {"auto", "manual"} else None,
                "decision": decision,
                "score": best.total_score if best else 0,
            }
        )
        if decision in {"auto", "manual"} and best:
            matches_by_polity[best.polity_id].append(str(row["seshat_id"]))
        elif decision == "unmatched":
            unmatched_drafts.append(
                {
                    "id": f"seshat_{normalize_name(str(row['canonical_name'])).replace(' ', '_')}_{str(row['seshat_id']).lower()}",
                    "canonical_name": row["canonical_name"],
                    "external_ids": {"seshat": [row["seshat_id"]]},
                    "start": int(row["start_year"]),
                    "end": int(row["end_year"]),
                    "start_confidence": row["start_confidence"],
                    "end_confidence": row["end_confidence"],
                    "notes": "Seshat-only draft; requires review before canonical import.",
                    "sources": ["seshat"],
                }
            )

    if apply:
        current_seshat_ids = set(seshat["seshat_id"].astype(str))
        changed: set[str] = set()
        for polity_id, (_, document) in documents.items():
            external_ids = document.setdefault("external_ids", {})
            existing = external_ids.get("seshat", [])
            if isinstance(existing, str):
                existing = [existing]
            retained = sorted(set(existing) - current_seshat_ids)
            if retained:
                if retained != existing:
                    external_ids["seshat"] = retained
                    changed.add(polity_id)
            elif "seshat" in external_ids:
                external_ids.pop("seshat")
                changed.add(polity_id)
            if not retained and "seshat" in document.get("sources", []) and existing:
                document["sources"] = [source for source in document["sources"] if source != "seshat"]
                changed.add(polity_id)
        for polity_id, seshat_ids in matches_by_polity.items():
            _, document = documents[polity_id]
            external_ids = document.setdefault("external_ids", {})
            existing = external_ids.get("seshat", [])
            if isinstance(existing, str):
                existing = [existing]
            external_ids["seshat"] = sorted(set(existing) | set(seshat_ids))
            document["sources"] = sorted(set(document.get("sources", [])) | {"seshat"})
            changed.add(polity_id)
        for polity_id in changed:
            path, document = documents[polity_id]
            path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.write_text(
        "".join(json.dumps(result, ensure_ascii=False) + "\n" for result in results), encoding="utf-8"
    )
    pd.DataFrame(crosswalk).to_parquet(CROSSWALK_PATH, index=False)
    UNMATCHED_PATH.write_text(
        yaml.safe_dump_all(unmatched_drafts, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    counts = Counter(result["decision"] for result in results)
    by_century: dict[int, Counter] = defaultdict(Counter)
    for result in results:
        century = (int(result["start_year"]) // 100) * 100
        by_century[century][result["decision"]] += 1
    lines = ["# Seshat reconciliation", "", "## Decisions", ""]
    decision_order = ("auto", "manual", "review", "rejected", "unmatched")
    lines.extend(f"- {decision.title()}: {counts[decision]:,}" for decision in decision_order)
    lines.extend(
        [
            "",
            "## By start century",
            "",
            "| Century | Auto | Manual | Review | Rejected | Unmatched |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for century, century_counts in sorted(by_century.items()):
        lines.append(
            f"| {century} | {century_counts['auto']} | {century_counts['manual']} | "
            f"{century_counts['review']} | {century_counts['rejected']} | "
            f"{century_counts['unmatched']} |"
        )
    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: counts[key] for key in decision_order}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-apply", action="store_true")
    args = parser.parse_args()
    counts = run(apply=not args.no_apply)
    print("Reconciliation: " + ", ".join(f"{key}={value}" for key, value in counts.items()))


if __name__ == "__main__":
    main()
