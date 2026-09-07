import tempfile
import unittest
from pathlib import Path

import yaml

from pipeline.drop_defunct_country_codes import main


class DropDefunctCountryCodesTests(unittest.TestCase):
    def test_drops_su_when_a_real_code_sits_alongside_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "georgian_ssr.yaml").write_text(
                yaml.safe_dump({
                    "id": "georgian_ssr",
                    "geography": {"present_countries": ["GE", "SU"]},
                }),
                encoding="utf-8",
            )

            summary = main(root)

            updated = yaml.safe_load(
                (root / "polities" / "georgian_ssr.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["present_countries"], ["GE"])
            self.assertIn("geography", updated["manual_overrides"])
            self.assertEqual(summary["polities_fixed"], 1)

    def test_bare_su_on_gorno_altai_is_corrected_to_russia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "gorno_altai_autonomous_soviet_socialist_republic.yaml").write_text(
                yaml.safe_dump({
                    "id": "gorno_altai_autonomous_soviet_socialist_republic",
                    "geography": {"present_countries": ["SU"]},
                }),
                encoding="utf-8",
            )

            main(root)

            updated = yaml.safe_load(
                (root / "polities" / "gorno_altai_autonomous_soviet_socialist_republic.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(updated["geography"]["present_countries"], ["RU"])

    def test_drops_cs_and_dd_the_same_way(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "czechoslovakia.yaml").write_text(
                yaml.safe_dump({"id": "czechoslovakia", "geography": {"present_countries": ["CS", "CZ"]}}),
                encoding="utf-8",
            )
            (root / "polities" / "german_democratic_republic.yaml").write_text(
                yaml.safe_dump({"id": "german_democratic_republic", "geography": {"present_countries": ["DD", "DE"]}}),
                encoding="utf-8",
            )

            summary = main(root)

            self.assertEqual(
                yaml.safe_load((root / "polities" / "czechoslovakia.yaml").read_text(encoding="utf-8"))
                ["geography"]["present_countries"],
                ["CZ"],
            )
            self.assertEqual(
                yaml.safe_load((root / "polities" / "german_democratic_republic.yaml").read_text(encoding="utf-8"))
                ["geography"]["present_countries"],
                ["DE"],
            )
            self.assertEqual(summary["polities_fixed"], 2)

    def test_yugoslavia_is_untouched(self) -> None:
        # YU is deliberately kept as a legitimate present_countries code
        # (see historical_regions.py) -- not a defunct code this script
        # should ever touch.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "yugoslavia.yaml").write_text(
                yaml.safe_dump({"id": "yugoslavia", "geography": {"present_countries": ["YU"]}}),
                encoding="utf-8",
            )

            summary = main(root)

            self.assertEqual(
                yaml.safe_load((root / "polities" / "yugoslavia.yaml").read_text(encoding="utf-8"))
                ["geography"]["present_countries"],
                ["YU"],
            )
            self.assertEqual(summary["polities_fixed"], 0)

    def test_record_without_a_defunct_code_is_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "polities" / "france.yaml").write_text(
                yaml.safe_dump({"id": "france", "geography": {"present_countries": ["FR"]}}),
                encoding="utf-8",
            )

            summary = main(root)

            self.assertEqual(summary["polities_fixed"], 0)

    def test_applies_to_periods_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "polities").mkdir()
            (root / "periods").mkdir()
            (root / "periods" / "some_period.yaml").write_text(
                yaml.safe_dump({"id": "some_period", "geography": {"present_countries": ["RU", "SU"]}}),
                encoding="utf-8",
            )

            summary = main(root)

            self.assertEqual(summary["periods_fixed"], 1)
            self.assertEqual(
                yaml.safe_load((root / "periods" / "some_period.yaml").read_text(encoding="utf-8"))
                ["geography"]["present_countries"],
                ["RU"],
            )


if __name__ == "__main__":
    unittest.main()
