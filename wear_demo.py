"""Demonstrate the dedicated-plate wear batch end to end.

Runs through the real loopback HTTP services:

* the original workshop day is replayed first, so the pre-batch regression is
  still visible;
* a two-impression batch shows a first press that loses its reply while the
  issue service is offline, reconciliation freeing one impression, a second
  paper signing while the press is offline, and both papers sharing the plate;
* a one-impression batch shows the two terminal endings of a paper whose short
  sequence is complete but whose longer alternative still allows one more press:
  returning before that press frees the impression, while taking it spends it.
"""

from tempfile import TemporaryDirectory

from day import run_day
from runtime import encode
import wear_fixture as wear


def _summary(value):
    return encode(value)


def main():
    with TemporaryDirectory(prefix='workshop-day-') as root:
        original = run_day(root)
        print('ORIGINAL_DAY ' + _summary({
            'revised': original['revised']['sequence'],
            'original': original['original']['sequence'],
            'returned': original['returned']['paper']}))

    with TemporaryDirectory(prefix='wear-batch-') as root:
        batch = wear.observe_v2(root)
        print('BATCH_BEFORE ' + _summary(batch['before']))
        print('BATCH_SIGN_Q_REFUSED ' + _summary({'code': batch['refused_early'], 'free': batch['before']['free']}))
        print('BATCH_AFTER_RECONCILE ' + _summary(batch['after_p']))
        print('BATCH_SIGN_Q_ACCEPTED ' + _summary(batch['accepted_q']))
        print('BATCH_SIGNED_Q ' + _summary(batch['signed_q']))
        print('BATCH_FIRST_RECEIPT ' + _summary(batch['first_receipt']))
        print('BATCH_PRESSED_P ' + _summary([row['step']['plate'] for row in batch['impressions_p']]))
        print('BATCH_PRESSED_Q ' + _summary([row['step']['plate'] for row in batch['impressions_q']]))
        print('BATCH_SETTLED ' + _summary(batch['settled']))
        print('BATCH_REOPEN_P ' + _summary(batch['recovered_p']))
        print('BATCH_REOPEN_Q ' + _summary(batch['recovered_q']))

    for continued in (False, True):
        with TemporaryDirectory(prefix='wear-edge-') as root:
            edge = wear.observe_edge(root, continue_after_c=continued)
            print('EDGE_AFTER_C ' + _summary(edge['pre']))
            print('EDGE_' + ('CONTINUE' if continued else 'RETURN') + ' ' + _summary({
                'piece': edge['piece']['sequence'],
                'balance': edge['after'],
                'reconcile_again': edge['reconcile_again']}))


if __name__ == '__main__':
    main()
