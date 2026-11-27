import json
from dataclasses import dataclass

from issue.orders import read_order
from runtime import Problem, encode


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS amendments (
        paper TEXT NOT NULL REFERENCES orders(paper), request_id TEXT NOT NULL,
        original TEXT NOT NULL REFERENCES editions(edition), candidate TEXT NOT NULL REFERENCES editions(edition),
        status TEXT NOT NULL CHECK(status IN ('pending', 'adopted', 'incompatible')),
        decision TEXT, PRIMARY KEY(paper, request_id)
    )''',
    '''CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_paper
       ON amendments(paper) WHERE status = 'pending' ''',
)


@dataclass(frozen=True)
class AmendmentRecord:
    paper: str
    request_id: str
    original: str
    candidate: str
    status: str
    decision: dict | None


def _read(db, paper, request_id):
    row = db.execute('SELECT * FROM amendments WHERE paper = ? AND request_id = ?',
                     (paper, request_id)).fetchone()
    if row is None:
        return None
    result = dict(row)
    if result['decision'] is not None:
        result['decision'] = json.loads(result['decision'])
    return AmendmentRecord(**result)


def read_request_status(db, paper, request_id):
    record = _read(db, paper, request_id)
    if record is None:
        raise Problem('unknown_amendment', 'No amendment with this paper and request number', 404)
    return record


def has_pending_request(db, paper):
    return db.execute('SELECT 1 FROM amendments WHERE paper = ? AND status = ?',
                      (paper, 'pending')).fetchone() is not None


def read_confirmed_edition(db, paper):
    order = read_order(db, paper)
    row = db.execute('''SELECT candidate, request_id FROM amendments
                        WHERE paper = ? AND status = 'adopted' ORDER BY rowid DESC LIMIT 1''',
                     (paper,)).fetchone()
    return (order.original, None) if row is None else (row['candidate'], row['request_id'])


def register_request(db, request):
    old = _read(db, request.paper, request.request_id)
    if old is not None:
        if (old.original, old.candidate) != (request.original, request.candidate):
            raise Problem('amendment_conflict', 'This request number has different parameters')
        return old
    edition, _ = read_confirmed_edition(db, request.paper)
    if has_pending_request(db, request.paper):
        raise Problem('amendment_pending', 'An earlier amendment for this paper is still pending')
    if request.original != edition:
        raise Problem('wrong_original', 'The original must be the confirmed edition of this paper')
    db.execute('''INSERT INTO amendments (paper, request_id, original, candidate, status)
                  VALUES (?, ?, ?, ?, 'pending')''',
               (request.paper, request.request_id, request.original, request.candidate))
    return read_request_status(db, request.paper, request.request_id)


def save_decision(db, record, decision):
    current = read_request_status(db, record.paper, record.request_id)
    keys = ('paper', 'request_id', 'original', 'candidate')
    if any(decision.get(key) != getattr(current, key) for key in keys):
        raise Problem('decision_conflict', 'The press decision refers to another amendment')
    if current.decision is not None:
        if current.decision != decision:
            raise Problem('decision_conflict', 'A different outcome is already recorded')
        return current
    status = decision.get('status')
    if status not in ('adopted', 'incompatible'):
        raise Problem('decision_conflict', 'The press response is missing a final outcome')
    edition, adoption_id = read_confirmed_edition(db, record.paper)
    if status == 'adopted':
        edition, adoption_id = record.candidate, record.request_id
    if (decision.get('edition'), decision.get('adoption_id')) != (edition, adoption_id):
        raise Problem('decision_conflict', 'The press decision names an inconsistent edition')
    db.execute('UPDATE amendments SET status = ?, decision = ? WHERE paper = ? AND request_id = ?',
               (status, encode(decision), record.paper, record.request_id))
    return read_request_status(db, record.paper, record.request_id)
