from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from runtime import encode, invoke, make_server, running


SAMPLE_PAPER = 'sample-return'
PLACEMENTS = {'A': 'top', 'B': 'middle', 'C': 'bottom', 'D': 'corner'}


def step(plate):
    return {'plate': plate, 'placement': PLACEMENTS[plate]}


def steps(plates):
    return [step(plate) for plate in plates]


def day_layouts():
    return [{'layout': 'lesson', 'placements': steps('ABCD'), 'sequences': [steps('ABC')]},
            {'layout': 'alternate', 'placements': steps('ABCD'), 'sequences': [steps('BA'), steps('AD')]}]


@dataclass
class Workshop:
    issue_service: object
    issue_url: str
    press_url: str

    def issue(self, route, **data):
        return invoke(self.issue_url, route, data)

    def press(self, route, **data):
        return invoke(self.press_url, route, data)


@contextmanager
def open_workshop(root, *, sample=False):
    from issue.service import IssueService
    from press.service import PressService

    root = Path(root)
    issue = IssueService(root / 'issue.sqlite', '', sample=sample)
    with running(make_server(issue.dispatch)) as issue_url:
        press = PressService(root / 'press.sqlite', issue_url, sample=sample)
        with running(make_server(press.dispatch)) as press_url:
            issue.press_url = press_url
            yield Workshop(issue, issue_url, press_url)


def editions(work):
    first = work.issue('freeze', layout='lesson', edition='E0')
    second = work.issue('freeze', layout='alternate', edition='E1')
    return first, second


def arrive(work, paper, edition='E0'):
    work.issue('issue', paper=paper, edition=edition)
    return work.press('stage', action='arrive', paper=paper, label=paper)


def mount(work, paper):
    return work.press('stage', action='mount', paper=paper, mount_id=f'mount:{paper}')


def ticket(work, paper, position, plate):
    return work.issue('ticket', paper=paper, position=position, step=step(plate))['ticket_id']


def print_step(work, paper, position, plate):
    number = ticket(work, paper, position, plate)
    receipt = work.press('press', paper=paper, ticket_id=number)
    assert work.issue('receive', paper=paper, ticket_id=number) == receipt
    return receipt


def finish(work, paper):
    work.press('stage', action='unmount', paper=paper, mount_id=f'mount:{paper}')
    return work.press('release', paper=paper)


def _emit(case_id, inputs, expected, actual, downstream_expected, downstream_actual, code_paths, oracle):
    assert actual == expected, (case_id, actual, expected)
    assert downstream_actual == downstream_expected, (case_id, downstream_actual, downstream_expected)
    print('POINTWISE_SCENARIO ' + encode({'case_id': case_id, 'input': inputs, 'expected': expected,
          'actual': actual, 'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
          'code_paths': code_paths, 'oracle': oracle}))


def run_day(root):
    with open_workshop(root, sample=True) as work:
        first, second = editions(work)
        work.issue('issue', paper='lesson-paper', edition='E0')
        draft = day_layouts()[0]
        draft['sequences'] = [steps('DC')]
        work.issue('layout', **draft)
        order = work.issue('order', paper='lesson-paper')
        assert order['edition'] == first and first['sequences'] == [steps('ABC')]
        returned = work.press('stage', action='return', paper=SAMPLE_PAPER)
        assert returned['paper'] == SAMPLE_PAPER
        arrive(work, 'lesson-paper')
        mount(work, 'lesson-paper')
        a = print_step(work, 'lesson-paper', 1, 'A')
        replay = work.press('press', paper='lesson-paper', ticket_id=a['ticket_id'])
        assert a == replay and len(work.press('impressions', paper='lesson-paper')) == 1
        amendment = work.issue('amend', paper='lesson-paper', original='E0', candidate='E1', request_id='lesson-change')
        assert work.issue('amend.status', paper='lesson-paper', request_id='lesson-change') == amendment
        d = print_step(work, 'lesson-paper', 2, 'D')
        changed = finish(work, 'lesson-paper')
        _emit('v5', {'prefix': [a['step']], 'alternatives': second['sequences']},
              'adopted', amendment['status'],
              {'edition': 'E1', 'sequence': steps('AD'), 'origins': ['E0', 'E1']},
              {'edition': changed['edition'], 'sequence': changed['sequence'],
               'origins': [source['edition'] for source in changed['sources']]},
              ['proof/sequences.py', 'press/adoption.py', 'issue/lookup.py', 'handoff/provenance.py'],
              '逐项手核：A 与第一条的 B 不同，第二条为 A、D，先印的 A 和后印的 D 各保留出处')
        assert [source['receipt_id'] for source in changed['sources']] == [a['receipt_id'], d['receipt_id']]

        arrive(work, 'original-paper')
        mount(work, 'original-paper')
        first_a = print_step(work, 'original-paper', 1, 'A')
        first_b = print_step(work, 'original-paper', 2, 'B')
        rejected = work.issue('amend', paper='original-paper', original='E0', candidate='E1', request_id='original-change')
        first_c = print_step(work, 'original-paper', 3, 'C')
        original = finish(work, 'original-paper')
        _emit('v6', {'prefix': [first_a['step'], first_b['step']], 'alternatives': second['sequences']},
              'incompatible', rejected['status'], steps('ABC'), original['sequence'],
              ['press/progress.py', 'press/adoption.py', 'issue/tickets.py', 'handoff/release.py'],
              '逐项手核：B、A 首位不同，A、D 次位不同。原稿次位 B 后仍可压 C')
        assert [source['receipt_id'] for source in original['sources']] == [item['receipt_id'] for item in (first_a, first_b, first_c)]

    with open_workshop(root, sample=True) as work:
        recovered = work.press('pickup', piece_id=original['piece_id'])
        assert work.press('pickup', piece_id=changed['piece_id']) == changed
        pickup = work.press('pickup.history', piece_id=original['piece_id'])
        assert [entry['piece_id'] for entry in pickup] == [original['piece_id']]
        assert work.issue('layout.read', layout='lesson')['sequences'] == [steps('DC')]
        _emit('v8', {'piece_id': original['piece_id'], 'reopened': True},
              original, recovered, steps('ABC'), recovered['sequence'],
              ['handoff/release.py', 'handoff/history.py'],
              '按重开前正式签件逐字段比对；实际印序按三笔原执手工核对为 A、B、C')
    return {'revised': changed, 'original': recovered, 'returned': returned}


if __name__ == '__main__':
    with TemporaryDirectory(prefix='workshop-day-') as root:
        print(encode(run_day(root)))
