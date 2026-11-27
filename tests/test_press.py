import unittest
from tempfile import TemporaryDirectory

from day import arrive, editions, mount, open_workshop, print_step, step, ticket
from runtime import Problem


class PressTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.work = self.enterContext(open_workshop(root, sample=True))
        editions(self.work)

    def test_print_and_original_receipt(self):
        arrive(self.work, 'J')
        mount(self.work, 'J')
        receipt = print_step(self.work, 'J', 1, 'A')
        self.assertEqual(self.work.press('press', paper='J', ticket_id=receipt['ticket_id']), receipt)
        self.assertEqual(self.work.issue('receive', paper='J', ticket_id=receipt['ticket_id']), receipt)
        self.assertEqual(self.work.issue('received', paper='J'), [receipt])
        impressions = self.work.press('impressions', paper='J')
        self.assertEqual([row['step'] for row in impressions], [step('A')])
        self.assertEqual(impressions[0]['mount_id'], 'mount:J')

    def test_out_of_order_is_not_an_impression(self):
        arrive(self.work, 'J')
        mount(self.work, 'J')
        b = ticket(self.work, 'J', 2, 'B')
        with self.assertRaises(Problem) as error:
            self.work.press('press', paper='J', ticket_id=b)
        self.assertEqual(error.exception.code, 'out_of_order')
        self.assertEqual(self.work.press('impressions', paper='J'), [])
        with self.assertRaises(Problem) as error:
            self.work.press('receipt', paper='J', ticket_id=b)
        self.assertEqual(error.exception.code, 'unknown_receipt')
        print_step(self.work, 'J', 1, 'A')
        self.assertEqual(self.work.press('press', paper='J', ticket_id=b)['step'], step('B'))

    def test_wrong_actual_paper(self):
        arrive(self.work, 'J')
        arrive(self.work, 'K')
        mount(self.work, 'K')
        a = ticket(self.work, 'J', 1, 'A')
        for paper in ('J', 'K'):
            with self.subTest(paper=paper), self.assertRaises(Problem) as error:
                self.work.press('press', paper=paper, ticket_id=a)
            self.assertEqual(error.exception.code, 'wrong_paper')
            self.assertEqual(self.work.press('impressions', paper=paper), [])
            with self.assertRaises(Problem) as error:
                self.work.press('receipt', paper=paper, ticket_id=a)
            self.assertEqual(error.exception.code, 'unknown_receipt')

    def test_return_before_mount_and_no_remount(self):
        self.work.issue('issue', paper='J', edition='E0')
        with self.assertRaises(Problem) as error:
            self.work.press('stage', paper='J', action='arrive', label='K')
        self.assertEqual(error.exception.code, 'wrong_paper')
        arrive(self.work, 'J')
        returned = self.work.press('stage', paper='J', action='return')
        self.assertEqual(returned, {'paper': 'J', 'return_id': 'return:J'})
        self.assertEqual(arrive(self.work, 'J')['state'], 'returned')
        with self.assertRaises(Problem) as error:
            mount(self.work, 'J')
        self.assertEqual(error.exception.code, 'not_mountable')
        status = self.work.press('stage.status', paper='J')
        self.assertEqual(status['arrival']['state'], 'returned')
        self.assertEqual(status['return'], returned)
        self.assertEqual(status['mounts'], [])
        self.assertEqual(self.work.press('impressions', paper='J'), [])
