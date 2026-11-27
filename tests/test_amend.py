import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from day import arrive, editions, finish, mount, open_workshop, print_step, steps, ticket
from runtime import LocalServer, Problem, Unavailable, invoke, running


@contextmanager
def cut_reply(upstream, operation, *, deliver):
    destination = urlsplit(upstream)

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            selected = self.path == f'/{operation}'
            if selected and not deliver:
                self.close_connection = True
                return
            connection = HTTPConnection(destination.hostname, destination.port, timeout=5)
            try:
                connection.request('POST', self.path, body, {'Content-Type': 'application/json'})
                response = connection.getresponse()
                payload = response.read()
                status = response.status
            finally:
                connection.close()
            if selected:
                self.close_connection = True
                return
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with running(LocalServer(('127.0.0.1', 0), Relay)) as url:
        yield url


class AmendTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(TemporaryDirectory())
        self.params = {'paper': 'J', 'original': 'E0', 'candidate': 'E1', 'request_id': 'change'}
        self.key = {'paper': 'J', 'request_id': 'change'}

    def prepare(self, work):
        editions(work)
        arrive(work, 'J')
        mount(work, 'J')

    def test_matches_second_alternative(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            a = print_step(work, 'J', 1, 'A')
            result = work.issue('amend', **self.params)
            self.assertEqual(result['status'], 'adopted')
            self.assertEqual(result['decision']['prefix'], steps('A'))
            self.assertEqual(work.issue('amend.status', **self.key), result)
            d = print_step(work, 'J', 2, 'D')
            self.assertEqual(work.press('press', paper='J', ticket_id=a['ticket_id']), a)
            self.assertEqual([a['edition'], d['edition']], ['E0', 'E1'])
            self.assertEqual(finish(work, 'J')['sequence'], steps('AD'))

    def test_empty_prefix(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            result = work.issue('amend', **self.params)
            self.assertEqual(result['status'], 'adopted')
            self.assertEqual(result['decision']['prefix'], [])
            print_step(work, 'J', 1, 'B')
            print_step(work, 'J', 2, 'A')
            self.assertEqual(finish(work, 'J')['sequence'], steps('BA'))

    def test_incompatible_visible_prefix(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            print_step(work, 'J', 1, 'A')
            print_step(work, 'J', 2, 'B')
            result = work.issue('amend', **self.params)
            self.assertEqual(result['status'], 'incompatible')
            self.assertEqual(result['decision']['prefix'], steps('AB'))
            self.assertEqual(work.issue('amend.status', **self.key), result)
            self.assertEqual(print_step(work, 'J', 3, 'C')['edition'], 'E0')
            self.assertEqual(finish(work, 'J')['sequence'], steps('ABC'))

    def test_pending_can_resume(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            original_link = work.press_url
            with cut_reply(original_link, 'adopt', deliver=False) as relay:
                work.issue_service.press_url = relay
                self.assertEqual(work.issue('amend', **self.params)['status'], 'pending')
                self.assertEqual(work.issue('amend.status', **self.key)['status'], 'pending')
                self.assertIsNone(work.press('adopt.status', **self.key))
                with self.assertRaises(Problem) as error:
                    ticket(work, 'J', 2, 'D')
                self.assertEqual(error.exception.code, 'amendment_pending')
            work.issue_service.press_url = original_link
            self.assertEqual(work.issue('amend.status', **self.key)['status'], 'pending')
            result = work.issue('amend', **self.params)
            self.assertEqual(result['status'], 'adopted')
            self.assertEqual(work.issue('amend', **self.params), result)
            with self.assertRaises(Problem) as error:
                work.issue('amend', **{**self.params, 'candidate': 'sample-edition'})
            self.assertEqual(error.exception.code, 'amendment_conflict')

    def test_adoption_first(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            a = ticket(work, 'J', 1, 'A')
            b = ticket(work, 'J', 2, 'B')
            with cut_reply(work.press_url, 'press', deliver=True) as relay:
                with self.assertRaises(Unavailable):
                    invoke(relay, 'press', {'paper': 'J', 'ticket_id': a})
            origin = work.press('receipt', paper='J', ticket_id=a)
            self.assertEqual(work.issue('received', paper='J'), [])
            with cut_reply(work.press_url, 'adopt', deliver=True) as relay:
                work.issue_service.press_url = relay
                self.assertEqual(work.issue('amend', **self.params)['status'], 'pending')
                decision = work.press('adopt.status', **self.key)
                self.assertEqual(decision['status'], 'adopted')
                self.assertEqual(decision['prefix'], steps('A'))
        with open_workshop(self.root) as work:
            self.assertEqual(work.issue('amend.status', **self.key)['decision'], decision)
            with self.assertRaises(Problem) as error:
                work.press('press', paper='J', ticket_id=b)
            self.assertEqual(error.exception.code, 'stale_ticket')
            self.assertEqual(work.press('press', paper='J', ticket_id=a), origin)
            self.assertEqual(work.issue('receive', paper='J', ticket_id=a), origin)
            d = print_step(work, 'J', 2, 'D')
            piece = finish(work, 'J')
            self.assertEqual(piece['sequence'], steps('AD'))
            self.assertEqual(piece['edition'], 'E1')
            self.assertEqual([(row['edition'], row['ticket_id'], row['receipt_id']) for row in piece['sources']],
                             [('E0', a, origin['receipt_id']), ('E1', d['ticket_id'], d['receipt_id'])])

    def test_impression_first(self):
        with open_workshop(self.root, sample=True) as work:
            self.prepare(work)
            a = print_step(work, 'J', 1, 'A')
            b = ticket(work, 'J', 2, 'B')
            with cut_reply(work.press_url, 'press', deliver=True) as relay:
                with self.assertRaises(Unavailable):
                    invoke(relay, 'press', {'paper': 'J', 'ticket_id': b})
            b_receipt = work.press('receipt', paper='J', ticket_id=b)
            self.assertEqual(work.issue('received', paper='J'), [a])
            amendment = work.issue('amend', **self.params)
            self.assertEqual(amendment['status'], 'incompatible')
            self.assertEqual(amendment['decision']['prefix'], steps('AB'))
            self.assertEqual(work.issue('amend.status', **self.key), amendment)
            with self.assertRaises(Problem) as error:
                ticket(work, 'J', 2, 'D')
            self.assertEqual(error.exception.code, 'step_not_in_edition')
            self.assertEqual(work.press('press', paper='J', ticket_id=b), b_receipt)
            c = print_step(work, 'J', 3, 'C')
            piece = finish(work, 'J')
            self.assertEqual(piece['sequence'], steps('ABC'))
            self.assertEqual(piece['edition'], 'E0')
            self.assertEqual([row['edition'] for row in piece['sources']], ['E0', 'E0', 'E0'])
            self.assertEqual([row['receipt_id'] for row in piece['sources']],
                             [a['receipt_id'], b_receipt['receipt_id'], c['receipt_id']])
