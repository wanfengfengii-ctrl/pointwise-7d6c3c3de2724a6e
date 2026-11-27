import unittest
from tempfile import TemporaryDirectory

from day import arrive, editions, finish, mount, open_workshop, print_step, steps
from runtime import Problem


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(TemporaryDirectory())

    def prepare(self, work):
        editions(work)
        arrive(work, 'J')
        mount(work, 'J')

    def test_partial_sequence_cannot_be_released(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            print_step(work, 'J', 1, 'A')
            with self.assertRaises(Problem) as error:
                work.press('stage', paper='J', action='unmount', mount_id='mount:J')
            self.assertEqual(error.exception.code, 'incomplete')
            with self.assertRaises(Problem) as error:
                work.press('release', paper='J')
            self.assertEqual(error.exception.code, 'incomplete')
            with self.assertRaises(Problem) as error:
                work.press('pickup', piece_id='piece:J')
            self.assertEqual(error.exception.code, 'unknown_piece')
            status = work.press('stage.status', paper='J')
            self.assertTrue(status['mounts'][0]['active'])
            self.assertIsNone(status['unmount'])

    def test_original_piece_after_reopen(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            receipts = [print_step(work, 'J', position, plate) for position, plate in enumerate('ABC', 1)]
            with self.assertRaises(Problem) as error:
                work.press('release', paper='J')
            self.assertEqual(error.exception.code, 'not_unmounted')
            with self.assertRaises(Problem) as error:
                work.press('stage', paper='J', action='unmount', mount_id='wrong')
            self.assertEqual(error.exception.code, 'wrong_mount')
            piece = finish(work, 'J')
            self.assertEqual(piece['sequence'], steps('ABC'))
            self.assertEqual(piece['edition'], 'E0')
            self.assertEqual([row['receipt_id'] for row in piece['sources']], [row['receipt_id'] for row in receipts])
        with open_workshop(self.root) as work:
            self.assertEqual(work.press('pickup', piece_id=piece['piece_id']), piece)
            self.assertEqual(work.press('release', paper='J'), piece)
            self.assertEqual(work.press('pickup', piece_id=piece['piece_id']), piece)
            history = work.press('pickup.history', piece_id=piece['piece_id'])
            self.assertEqual([entry['pickup_id'] for entry in history], [1, 2])

    def test_carried_origin(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            a = print_step(work, 'J', 1, 'A')
            result = work.issue('amend', paper='J', original='E0', candidate='E1', request_id='new')
            self.assertEqual(result['status'], 'adopted')
            d = print_step(work, 'J', 2, 'D')
            piece = finish(work, 'J')
            self.assertEqual(piece['edition'], 'E1')
            self.assertEqual(piece['sequence'], steps('AD'))
            for position, receipt, source, edition in zip((1, 2), (a, d), piece['sources'], ('E0', 'E1'), strict=True):
                self.assertEqual(source, {'position': position, 'step': receipt['step'], 'edition': edition,
                                          'ticket_id': receipt['ticket_id'], 'receipt_id': receipt['receipt_id'],
                                          'mount_id': 'mount:J'})
            self.assertEqual(work.press('press', paper='J', ticket_id=a['ticket_id']), a)

    def test_complete_short_alternative_allows_longer_before_unmount(self):
        with open_workshop(self.root, sample=True) as work:
            work.issue('layout', layout='short-or-long', placements=steps('AD'), sequences=[steps('A'), steps('AD')])
            work.issue('freeze', layout='short-or-long', edition='short-or-long')
            arrive(work, 'J', 'short-or-long')
            mount(work, 'J')
            print_step(work, 'J', 1, 'A')
            print_step(work, 'J', 2, 'D')
            self.assertEqual(finish(work, 'J')['sequence'], steps('AD'))
            arrive(work, 'K', 'short-or-long')
            mount(work, 'K')
            print_step(work, 'K', 1, 'A')
            self.assertEqual(finish(work, 'K')['sequence'], steps('A'))
