import unittest
from tempfile import TemporaryDirectory

from day import day_layouts, editions, open_workshop, steps
from runtime import Problem


class IssueTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.work = self.enterContext(open_workshop(root, sample=True))

    def test_frozen_order_survives_working_edit(self):
        first, _ = editions(self.work)
        self.work.issue('issue', paper='J', edition='E0')
        draft = day_layouts()[0]
        draft['sequences'] = [steps('DAC')]
        self.work.issue('layout', **draft)
        self.assertEqual(self.work.issue('layout.read', layout='lesson')['sequences'], [steps('DAC')])
        order = self.work.issue('order', paper='J')
        self.assertEqual(order['original'], 'E0')
        self.assertEqual(order['edition']['sequences'], [steps('ABC')])
        self.assertEqual(self.work.issue('edition', edition='E0'), first)
        with self.assertRaises(Problem) as error:
            self.work.issue('freeze', layout='lesson', edition='E0')
        self.assertEqual(error.exception.code, 'edition_conflict')

    def test_bad_references_and_empty_sequences_do_not_freeze(self):
        cases = [('placement', [steps('A') + [{'plate': 'B', 'placement': 'unknown'}]], 'unknown_placement'),
                 ('plate', [steps('A') + [{'plate': 'Z', 'placement': 'middle'}]], 'unknown_plate'),
                 ('empty', [], 'empty_sequence'), ('empty_alternative', [steps('A'), []], 'empty_sequence')]
        for name, sequences, code in cases:
            with self.subTest(name=name):
                self.work.issue('layout', layout='bad', placements=steps('ABCD'), sequences=sequences)
                with self.assertRaises(Problem) as error:
                    self.work.issue('freeze', layout='bad', edition=name)
                self.assertEqual(error.exception.code, code)
                with self.assertRaises(Problem) as error:
                    self.work.issue('issue', paper=name, edition=name)
                self.assertEqual(error.exception.code, 'unknown_edition')
                with self.assertRaises(Problem) as error:
                    self.work.issue('order', paper=name)
                self.assertEqual(error.exception.code, 'unknown_order')
