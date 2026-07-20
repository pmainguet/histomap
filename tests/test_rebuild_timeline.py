import unittest
from unittest.mock import patch

from pipeline import rebuild_timeline


class RebuildTimelineTests(unittest.TestCase):
    @patch("pipeline.rebuild_timeline.build.main")
    @patch("pipeline.rebuild_timeline.compute")
    def test_recomputes_prominence_offline_before_building(self, compute, build_main) -> None:
        compute.return_value = {"global": 1, "regional": 2, "detailed": 3}

        rebuild_timeline.main()

        compute.assert_called_once_with(offline=True)
        build_main.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
