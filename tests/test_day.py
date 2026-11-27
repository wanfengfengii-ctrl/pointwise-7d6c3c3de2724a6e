import unittest
from tempfile import TemporaryDirectory

from day import SAMPLE_PAPER, arrive, day_layouts, editions, mount, open_workshop, print_step, run_day, steps


class WorkshopDayTests(unittest.TestCase):
    def test_full_day(self):
        with TemporaryDirectory() as root:
            result = run_day(root)
        self.assertEqual(result['revised']['sequence'], steps('AD'))
        self.assertEqual(result['original']['sequence'], steps('ABC'))
        self.assertEqual(result['returned']['paper'], SAMPLE_PAPER)

    def test_repeat_initialization_preserves_modified_and_in_process_records(self):
        with TemporaryDirectory() as root:
            with open_workshop(root, sample=True) as work:
                editions(work)
                arrive(work, 'J')
                mount(work, 'J')
                receipt = print_step(work, 'J', 1, 'A')
                returned = work.press('stage', action='return', paper=SAMPLE_PAPER)
                changed = day_layouts()[0]
                changed['sequences'] = [steps('DAC')]
                work.issue('layout', **changed)
                work.issue('plate', plate='A', name='工坊新名')
            for sample in (False, True, True):
                with self.subTest(sample=sample), open_workshop(root, sample=sample) as work:
                    self.assertEqual(work.issue('layout.read', layout='lesson'), changed)
                    self.assertEqual(work.issue('order', paper='J')['edition']['sequences'], [steps('ABC')])
                    self.assertEqual(work.press('receipt', paper='J', ticket_id=receipt['ticket_id']), receipt)
                    self.assertEqual(work.issue('received', paper='J'), [receipt])
                    self.assertEqual(work.press('stage.status', paper=SAMPLE_PAPER)['return'], returned)
                    self.assertEqual([row['step'] for row in work.press('impressions', paper='J')], steps('A'))
