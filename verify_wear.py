"""Single verify entry: the full original regression plus the batch fixtures.

Runs ``check_project`` first (the untouched original unittest suite, now also
including ``tests/test_wear.py``), then replays each dedicated-plate scenario
against the real loopback services.  Any assertion failure propagates as a
non-zero exit, as required by WEAR.md.
"""

import sys
import traceback
from tempfile import TemporaryDirectory

import check_project
import wear_fixture as wear


def _scenario(name, function, *args, **kwargs):
    with TemporaryDirectory(prefix=f'wear-{name}-') as root:
        function(root, *args, **kwargs)
    print(f'WEAR_SCENARIO {name} ok')


def main():
    code = check_project.main()
    try:
        _scenario('v1-pre-batch', wear.observe_v1)
        _scenario('two-papers-share-B', wear.observe_v2)
        _scenario('edge-return', wear.observe_edge, continue_after_c=False)
        _scenario('edge-continue', wear.observe_edge, continue_after_c=True)
        _scenario('open-and-ordinary-rules', wear.observe_guard)
    except AssertionError:
        traceback.print_exc()
        print('WEAR_SCENARIO failed', file=sys.stderr)
        return 1
    return code


if __name__ == '__main__':
    raise SystemExit(main())
