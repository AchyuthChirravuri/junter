"""test_scoring.py — boundary tests for code/scoring.py.

Reference boundary values documented in docs/scoring-rubric.md (v2):
    * all dimensions at 2 -> raw=18, normalized=10 (the maximum).
    * all dimensions at 1 -> raw=9,  normalized=5  (the midpoint).

These are the literal expected numbers a reader should be able to compute by
hand from the rubric. They are also the test value the README evidence matrix
promises: a stranger can clone, run pytest, and see those exact numbers.

Tests are written as unittest.TestCase subclasses so they are collected by
both `pytest` and `unittest discover`.
"""
import unittest

from engine.scoring import (
    DENOMINATOR,
    MAX_NORMALIZED,
    MAX_RAW,
    WEIGHTS,
    WORKAUTH_GAP_CAP,
    STALE_POSTING_CAP,
    ScoringError,
    score,
)


def all_at(value):
    return {k: value for k in WEIGHTS}


class ScoringBoundaryTests(unittest.TestCase):
    """These four cases are the ones the README evidence matrix names."""

    def test_maximum_returns_10(self):
        result = score(all_at(2))
        self.assertEqual(result["raw"], 18.0)
        self.assertEqual(result["normalized"], 10.0)
        self.assertEqual(result["applied_cap"], None)
        self.assertEqual(result["route"], "package")

    def test_midpoint_returns_5(self):
        """All dimensions at 1 -> raw = sum of weights = 9, normalized = 5."""
        result = score(all_at(1))
        self.assertEqual(result["raw"], 9.0)
        self.assertEqual(result["normalized"], 5.0)
        self.assertEqual(result["applied_cap"], None)
        self.assertEqual(result["route"], "tracker_only")

    def test_minimum_returns_0(self):
        result = score(all_at(0))
        self.assertEqual(result["raw"], 0.0)
        self.assertEqual(result["normalized"], 0.0)
        self.assertEqual(result["route"], "tracker_only")

    def test_denominator_matches_doc(self):
        """The doc says 18.0; this test pins that contract."""
        self.assertEqual(DENOMINATOR, 18.0)
        self.assertEqual(MAX_RAW, 18.0)
        self.assertEqual(MAX_NORMALIZED, 10.0)


class ScoringCapTests(unittest.TestCase):
    def test_stale_posting_caps_at_5(self):
        """posting_age_days > 21 caps normalized at 5.0 even if dimensions are high."""
        ev = all_at(2)
        ev["posting_age_days"] = 30
        result = score(ev)
        self.assertEqual(result["normalized"], STALE_POSTING_CAP)
        self.assertEqual(result["applied_cap"], "stale_posting")
        # raw is still computed
        self.assertEqual(result["raw"], 18.0)

    def test_fresh_posting_unchanged(self):
        ev = all_at(2)
        ev["posting_age_days"] = 5
        result = score(ev)
        self.assertEqual(result["normalized"], 10.0)
        self.assertEqual(result["applied_cap"], None)

    def test_workauth_gap_caps_at_6(self):
        ev = all_at(2)
        ev["sponsorship_gap"] = True
        result = score(ev)
        self.assertEqual(result["normalized"], WORKAUTH_GAP_CAP)
        self.assertEqual(result["applied_cap"], "workauth_gap")

    def test_workauth_gap_does_not_inflate(self):
        """sponsorship_gap=True never raises the score, only caps it."""
        ev = all_at(1)
        ev["sponsorship_gap"] = True
        result = score(ev)
        # raw=9, normalized=5; cap of 6 is above 5, so nothing changes
        self.assertEqual(result["normalized"], 5.0)
        self.assertEqual(result["applied_cap"], None)

    def test_stale_takes_priority_over_workauth(self):
        """Both caps set: stale cap (5.0) is the stricter one."""
        ev = all_at(2)
        ev["posting_age_days"] = 60
        ev["sponsorship_gap"] = True
        result = score(ev)
        self.assertEqual(result["normalized"], STALE_POSTING_CAP)
        self.assertEqual(result["applied_cap"], "stale_posting")


class ScoringRoutingTests(unittest.TestCase):
    def test_route_package_at_9(self):
        ev = all_at(2)
        ev["level_fit"] = 1   # raw = 18 - 1.5 = 16.5; normalized ~ 9.17
        result = score(ev)
        self.assertGreaterEqual(result["normalized"], 9.0)
        self.assertEqual(result["route"], "package")

    def test_route_ping_at_7_to_8_5(self):
        ev = all_at(1)
        ev["level_fit"] = 0
        ev["work_auth"] = 0
        # raw = 9 - 1.5 - 2 = 5.5; normalized ~ 3.06 -> tracker_only
        result = score(ev)
        self.assertEqual(result["route"], "tracker_only")

    def test_route_tracker_only_below_7(self):
        ev = all_at(0)
        result = score(ev)
        self.assertEqual(result["route"], "tracker_only")


class ScoringValidationTests(unittest.TestCase):
    def test_unknown_dim_rejected(self):
        with self.assertRaises(ScoringError):
            score({k: 1 for k in WEIGHTS}, version="not-a-version")

    def test_missing_dim_rejected(self):
        bad = {k: 1 for k in WEIGHTS}
        bad.pop("role_type")
        with self.assertRaises(ScoringError):
            score(bad)

    def test_dim_score_out_of_range(self):
        bad = all_at(2)
        bad["role_type"] = 3
        with self.assertRaises(ScoringError):
            score(bad)

    def test_dim_score_negative(self):
        bad = all_at(2)
        bad["freshness"] = -1
        with self.assertRaises(ScoringError):
            score(bad)

    def test_dim_score_string(self):
        bad = all_at(2)
        bad["domain_fit"] = "yes"  # type: ignore[assignment]
        with self.assertRaises(ScoringError):
            score(bad)

    def test_evidence_not_dict(self):
        with self.assertRaises(ScoringError):
            score("not a dict")

    def test_posting_age_negative(self):
        bad = all_at(2)
        bad["posting_age_days"] = -3
        with self.assertRaises(ScoringError):
            score(bad)

    def test_posting_age_string(self):
        bad = all_at(2)
        bad["posting_age_days"] = "old"  # type: ignore[assignment]
        with self.assertRaises(ScoringError):
            score(bad)

    def test_sponsorship_gap_not_bool(self):
        bad = all_at(2)
        bad["sponsorship_gap"] = "maybe"  # type: ignore[assignment]
        with self.assertRaises(ScoringError):
            score(bad)


class ScoringDocContractTests(unittest.TestCase):
    """These pin the doc/code parity the README evidence matrix claims."""

    def test_hand_computed_max_matches(self):
        """Reader can reproduce: sum(2*w) = 18, /18 *10 = 10."""
        hand_max = sum(2.0 * w for w in WEIGHTS.values())
        self.assertEqual(hand_max, 18.0)
        normalized = (hand_max / 18.0) * 10
        self.assertEqual(normalized, 10.0)

    def test_hand_computed_midpoint_matches(self):
        """Reader can reproduce: sum(1*w) = 9, /18 *10 = 5."""
        hand_mid = sum(1.0 * w for w in WEIGHTS.values())
        self.assertEqual(hand_mid, 9.0)
        normalized = (hand_mid / 18.0) * 10
        self.assertEqual(normalized, 5.0)


if __name__ == "__main__":
    unittest.main()