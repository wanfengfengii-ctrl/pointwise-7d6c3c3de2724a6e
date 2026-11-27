import unittest
from tempfile import TemporaryDirectory

import wear_fixture as wear


class WearBatchTests(unittest.TestCase):
    def test_two_papers_share_dedicated_plate(self):
        with TemporaryDirectory() as root:
            observed = wear.observe_v2(root)
        self.assertEqual(observed["before"], {"batch": "W", "plate": "B", "total": 2,
                                              "used": 0, "held": 2, "free": 0})
        self.assertEqual(observed["after_p"], {"batch": "W", "plate": "B", "total": 2,
                                               "used": 0, "held": 1, "free": 1})
        self.assertEqual(observed["signed_q"], {"batch": "W", "plate": "B", "total": 2,
                                                "used": 0, "held": 2, "free": 0})
        self.assertEqual(observed["settled"], {"batch": "W", "plate": "B", "total": 2,
                                               "used": 2, "held": 0, "free": 0})
        self.assertEqual(observed["refused_early"], "insufficient_wear")
        self.assertEqual(observed["accepted_q"], {"batch": "W", "paper": "Q", "original": "one",
                                                  "request_id": "sign-Q"})
        self.assertEqual(observed["paper_P"]["sequence"], wear.steps("CB"))
        self.assertEqual(observed["paper_Q"]["sequence"], wear.steps("B"))

    def test_edge_returns_short_sequence_after_keeping_continuation(self):
        with TemporaryDirectory() as root:
            observed = wear.observe_edge(root, continue_after_c=False)
        self.assertEqual(observed["pre"], {"batch": "E", "plate": "B", "total": 1,
                                           "used": 0, "held": 1, "free": 0})
        self.assertEqual(observed["after"], {"batch": "E", "plate": "B", "total": 1,
                                             "used": 0, "held": 0, "free": 1})
        self.assertEqual(observed["reconcile_again"], observed["after"])
        self.assertEqual(observed["piece"]["sequence"], wear.steps("C"))

    def test_edge_continuation_costs_the_impression(self):
        with TemporaryDirectory() as root:
            observed = wear.observe_edge(root, continue_after_c=True)
        self.assertEqual(observed["pre"], {"batch": "E", "plate": "B", "total": 1,
                                           "used": 0, "held": 1, "free": 0})
        self.assertEqual(observed["after"], {"batch": "E", "plate": "B", "total": 1,
                                             "used": 1, "held": 0, "free": 0})
        self.assertEqual(observed["piece"]["sequence"], wear.steps("CB"))

    def test_open_and_ordinary_rules(self):
        with TemporaryDirectory() as root:
            observed = wear.observe_guard(root)
        self.assertEqual(observed["balance"], {"batch": "G", "plate": "D", "total": 1,
                                               "used": 0, "held": 0, "free": 1})
