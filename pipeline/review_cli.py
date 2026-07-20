"""Review ambiguous Seshat reconciliation candidates in the terminal."""

from __future__ import annotations

import json
import math
from pathlib import Path

import yaml

from pipeline.reconcile import DECISIONS_PATH, REVIEW_PATH, load_review_decisions


def polity_metadata(polities_dir: Path) -> dict[str, dict]:
    return {
        document["id"]: document
        for path in polities_dir.glob("*.yaml")
        for document in [yaml.safe_load(path.read_text(encoding="utf-8"))]
    }


def review_priority(record: dict, metadata: dict[str, dict]) -> tuple[float, dict[str, float]]:
    candidates = record.get("candidates", [])
    if not candidates:
        return 0.0, {
            key: 0.0
            for key in ("source_importance", "candidate_impact", "quality", "ambiguity", "tier", "coverage")
        }
    best = candidates[0]
    document = metadata.get(best["polity_id"], {})
    candidate_impact = float(document.get("prominence_score", 0))
    source_signals = []
    for key, scale in (
        ("peak_population_log10", 12.5),
        ("peak_area_km2_log10", 12.5),
        ("peak_social_complexity", 10.0),
    ):
        value = record.get(key)
        if value is not None and not (isinstance(value, float) and math.isnan(value)):
            source_signals.append(min(100.0, float(value) * scale))
    duration = max(1, int(record.get("end_year", 0)) - int(record.get("start_year", 0)) + 1)
    source_signals.append(min(100.0, 30 * math.log10(duration + 1)))
    source_importance = sum(source_signals) / len(source_signals)
    quality = float(best.get("total_score", 0))
    runner_up = float(candidates[1].get("total_score", 0)) if len(candidates) > 1 else 0.0
    margin = max(0.0, quality - runner_up)
    ambiguity = max(0.0, 100.0 - margin * 8)
    tier = {"global": 100.0, "regional": 50.0, "detailed": 0.0}.get(
        document.get("visibility_tier", "detailed"), 0.0
    )
    coverage = 0.0 if (document.get("external_ids") or {}).get("seshat") else 100.0
    components = {
        "source_importance": source_importance,
        "candidate_impact": candidate_impact,
        "quality": quality,
        "ambiguity": ambiguity,
        "tier": tier,
        "coverage": coverage,
    }
    score = (
        0.30 * source_importance
        + 0.25 * candidate_impact
        + 0.20 * quality
        + 0.10 * ambiguity
        + 0.10 * tier
        + 0.05 * coverage
    )
    return round(score, 2), components


def pending_records(
    review_path: Path = REVIEW_PATH,
    decisions_path: Path = DECISIONS_PATH,
    polities_dir: Path | None = None,
    metadata: dict[str, dict] | None = None,
) -> list[dict]:
    decisions = load_review_decisions(decisions_path)
    records = [
        json.loads(line)
        for line in review_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    pending = [
        record
        for record in records
        if record["decision"] == "review" and record["seshat_id"] not in decisions
    ]
    if metadata is None:
        metadata = polity_metadata(polities_dir or REVIEW_PATH.parent.parent / "polities")
    for record in pending:
        score, components = review_priority(record, metadata)
        record["review_priority"] = score
        record["priority_components"] = components
    return sorted(pending, key=lambda record: (-record["review_priority"], record["seshat_id"]))


def save_decision(decision: dict, path: Path = DECISIONS_PATH) -> None:
    decisions = load_review_decisions(path)
    decisions[decision["seshat_id"]] = decision
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False) + "\n" for _, value in sorted(decisions.items())),
        encoding="utf-8",
    )


def display(record: dict, position: int, total: int) -> None:
    print(
        f"\n[{position}/{total}] {record['seshat_name']} "
        f"({record['start_year']} to {record['end_year']}) [{record['seshat_id']}] "
        f"priority={record['review_priority']:.1f}"
    )
    components = record["priority_components"]
    print(
        "  priority: "
        f"source={components['source_importance']:.0f} "
        f"candidate={components['candidate_impact']:.0f} quality={components['quality']:.0f} "
        f"ambiguity={components['ambiguity']:.0f} tier={components['tier']:.0f} "
        f"coverage={components['coverage']:.0f}"
    )
    for number, candidate in enumerate(record["candidates"], start=1):
        print(
            f"  {number}. {candidate['canonical_name']} [{candidate['polity_id']}] "
            f"total={candidate['total_score']:.1f} name={candidate['name_score']:.1f} "
            f"date={candidate['date_score']:.1f} geo={candidate['geography_score']:.1f}"
        )
    print("Choose 1-5 to accept, r to reject all candidates, s to defer, q to quit.")


def main() -> None:
    records = pending_records()
    if not records:
        print("No pending Seshat reconciliation reviews.")
        return
    for position, record in enumerate(records, start=1):
        display(record, position, len(records))
        while True:
            choice = input("> ").strip().lower()
            if choice == "q":
                return
            if choice == "s":
                break
            if choice == "r":
                save_decision({"seshat_id": record["seshat_id"], "decision": "reject"})
                break
            if choice.isdigit() and 1 <= int(choice) <= len(record["candidates"]):
                candidate = record["candidates"][int(choice) - 1]
                save_decision(
                    {
                        "seshat_id": record["seshat_id"],
                        "decision": "accept",
                        "polity_id": candidate["polity_id"],
                    }
                )
                break
            print("Invalid choice.")
    print("Review decisions saved. Run the reconciliation command to apply them.")


if __name__ == "__main__":
    main()
