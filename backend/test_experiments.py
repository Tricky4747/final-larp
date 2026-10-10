"""Tests that outreach batches distribute active message variants."""

import tempfile
import unittest
from pathlib import Path

from experiments import Experiments


class VariantAllocationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.experiments = Experiments(
            path=Path(self.directory.name) / "experiments.db"
        )
        self.addCleanup(self.experiments.db.close)
        for variant in ("A", "B", "C", "D"):
            self.experiments.register(variant)

    def test_initial_batch_uses_each_active_variant_and_balances_counts(self):
        allocation = self.experiments.allocate(10)

        self.assertEqual(set(allocation), {"A", "B", "C", "D"})
        counts = [allocation.count(variant) for variant in ("A", "B", "C", "D")]
        self.assertLessEqual(max(counts) - min(counts), 1)

    def test_winner_does_not_stop_rotation(self):
        for _ in range(5):
            self.experiments.record("A", replied=True)
        self.experiments.retire("B")

        allocation = self.experiments.allocate(20)

        self.assertEqual(set(allocation), {"A", "B", "C", "D"})
        self.assertGreaterEqual(allocation.count("B"), 5)

    def test_rotation_continues_across_rounds(self):
        for variant in self.experiments.allocate(6):
            self.experiments.record(variant, replied=False)
        counts = [s["sends"] for s in self.experiments.stats().values()]
        self.assertLessEqual(max(counts) - min(counts), 1)

    def test_small_batch_does_not_repeat_a_variant_before_using_distinct_ones(self):
        allocation = self.experiments.allocate(3)

        self.assertEqual(len(allocation), len(set(allocation)))


if __name__ == "__main__":
    unittest.main()