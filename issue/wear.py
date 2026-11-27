"""Dedicated-plate wear batches on the issue side.

A batch reserves one registered plate for a fixed number of actual impressions.
Batch papers are signed against one fixed edition and are never amended.  The
ledger is derived only from verified press facts:

``used`` counts dedicated-plate impressions already verified, ``held`` is the
sum over each paper still on the press of the greatest remaining dedicated-plate
consumption among the fixed alternatives compatible with its verified prefix,
and ``free`` is ``total - used - held``.
"""

import json
from dataclasses import dataclass

from issue.orders import issue_order
from proof.freeze import read_frozen_edition
from proof.plates import require_plate
from proof.sequences import match_prefix
from proof.steps import parse_step, step_payload
from runtime import Problem, encode, positive, text


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS wear_batches (
        batch TEXT PRIMARY KEY, plate TEXT NOT NULL, total INTEGER NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS wear_papers (
        paper TEXT PRIMARY KEY, batch TEXT NOT NULL REFERENCES wear_batches(batch),
        edition TEXT NOT NULL REFERENCES editions(edition), request_id TEXT NOT NULL,
        UNIQUE(batch, request_id)
    )''',
    '''CREATE TABLE IF NOT EXISTS wear_verified (
        paper TEXT PRIMARY KEY, batch TEXT NOT NULL, steps TEXT NOT NULL,
        released INTEGER NOT NULL
    )''',
)


@dataclass(frozen=True)
class WearBatch:
    batch: str
    plate: str
    total: int


def _batch(db, batch):
    row = db.execute('SELECT * FROM wear_batches WHERE batch = ?', (batch,)).fetchone()
    if row is None:
        raise Problem('unknown_batch', f'No wear batch {batch}', 404)
    return WearBatch(row['batch'], row['plate'], row['total'])


def _batch_payload(record):
    return {'batch': record.batch, 'plate': record.plate, 'total': record.total}


def _paper_payload(row):
    return {'batch': row['batch'], 'paper': row['paper'],
            'original': row['edition'], 'request_id': row['request_id']}


def _plate_count(sequence, plate):
    return sum(1 for step in sequence if step.plate == plate)


def _required(sequences, plate):
    return max((_plate_count(sequence, plate) for sequence in sequences), default=0)


def _edition_uses(db, edition, plate):
    frozen = read_frozen_edition(db, edition)
    return any(step.plate == plate for sequence in frozen.sequences for step in sequence)


def reserved_plates(db):
    return {row['plate'] for row in db.execute('SELECT plate FROM wear_batches')}


def reject_reserved_edition(db, edition):
    """Ordinary orders and ordinary amendments may only use ordinary plates."""
    plates = reserved_plates(db)
    if not plates:
        return
    frozen = read_frozen_edition(db, edition)
    if any(step.plate in plates for sequence in frozen.sequences for step in sequence):
        raise Problem('reserved_plate', 'The dedicated plate is reserved for batch papers', 409)


def is_batch_paper(db, paper):
    return db.execute('SELECT 1 FROM wear_papers WHERE paper = ?', (paper,)).fetchone() is not None


def open_batch(db, batch, plate, total):
    batch = text(batch, 'batch')
    plate = text(plate, 'plate')
    total = positive(total, 'total')
    require_plate(db, plate)
    existing = db.execute('SELECT * FROM wear_batches WHERE batch = ?', (batch,)).fetchone()
    if existing is not None:
        if (existing['plate'], existing['total']) != (plate, total):
            raise Problem('batch_conflict', 'This batch number was opened with other parameters', 409)
        return _batch_payload(_batch(db, batch))
    for row in db.execute('SELECT original FROM orders'):
        if _edition_uses(db, row['original'], plate):
            raise Problem('plate_in_use', 'An existing paper order can use this plate', 409)
    for row in db.execute('SELECT candidate FROM amendments'):
        if _edition_uses(db, row['candidate'], plate):
            raise Problem('plate_in_use', 'An existing amendment candidate can use this plate', 409)
    db.execute('INSERT INTO wear_batches VALUES (?, ?, ?)', (batch, plate, total))
    return {'batch': batch, 'plate': plate, 'total': total}


def issue_wear_paper(db, data):
    batch = text(data.get('batch'), 'batch')
    paper = text(data.get('paper'), 'paper')
    edition = text(data.get('edition'), 'edition')
    request_id = text(data.get('request_id'), 'request_id')
    record = _batch(db, batch)
    frozen = read_frozen_edition(db, edition)
    by_request = db.execute('SELECT * FROM wear_papers WHERE batch = ? AND request_id = ?',
                            (batch, request_id)).fetchone()
    if by_request is not None:
        if (by_request['paper'], by_request['edition']) != (paper, edition):
            raise Problem('request_conflict', 'This request number signed other parameters', 409)
        return _paper_payload(by_request)
    if db.execute('SELECT 1 FROM wear_papers WHERE paper = ?', (paper,)).fetchone():
        raise Problem('paper_conflict', 'This paper already belongs to a wear batch', 409)
    if db.execute('SELECT 1 FROM orders WHERE paper = ?', (paper,)).fetchone():
        raise Problem('paper_conflict', 'This paper already has an order', 409)
    required = _required(frozen.sequences, record.plate)
    if compute_balance(db, batch)['free'] < required:
        raise Problem('insufficient_wear', 'Not enough dedicated-plate impressions remain', 409)
    issue_order(db, paper, edition)
    db.execute('INSERT INTO wear_papers VALUES (?, ?, ?, ?)', (paper, batch, edition, request_id))
    return {'batch': batch, 'paper': paper, 'original': edition, 'request_id': request_id}


def paper_by_paper(db, paper):
    row = db.execute('SELECT * FROM wear_papers WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        raise Problem('unknown_batch_paper', 'Paper is not signed into any wear batch', 404)
    return _paper_payload(row)


def paper_payload(db, batch, paper):
    row = db.execute('SELECT * FROM wear_papers WHERE batch = ? AND paper = ?',
                     (batch, paper)).fetchone()
    if row is None:
        raise Problem('unknown_batch_paper', 'Paper is not signed into this batch', 404)
    return _paper_payload(row)


def _read_verified(db, paper):
    row = db.execute('SELECT steps, released FROM wear_verified WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        return (), False
    steps = tuple(parse_step(step) for step in json.loads(row['steps']))
    return steps, bool(row['released'])


def record_verified(db, batch, paper, state):
    """Fold one press snapshot into the ledger, only ever moving forward.

    A snapshot is the atomic pair ``(steps, released)`` read from the press in
    one transaction.  A snapshot is accepted only if its step list extends the
    stored prefix; a shorter or divergent list is stale and ignored whole,
    including its release flag.  This is what keeps a pre-B impression count
    from ever being fused with a post-B unmount to free an allowance that was
    never spent.  Duplicates and late evidence therefore never release twice or
    restore an excluded order.
    """
    if state.get('batch') != batch or state.get('paper') != paper:
        raise Problem('state_conflict', 'The press state names another batch paper', 409)
    new_steps = tuple(parse_step(step) for step in state.get('steps', []))
    new_released = bool(state.get('released'))
    old_steps, old_released = _read_verified(db, paper)
    if len(new_steps) >= len(old_steps) and new_steps[:len(old_steps)] == old_steps:
        merged_steps = new_steps
        merged_released = old_released or new_released
    else:
        return
    encoded = encode([step_payload(step) for step in merged_steps])
    db.execute('''INSERT INTO wear_verified VALUES (?, ?, ?, ?)
                  ON CONFLICT(paper) DO UPDATE SET steps = excluded.steps,
                  released = excluded.released''',
               (paper, batch, encoded, 1 if merged_released else 0))


def compute_balance(db, batch):
    record = _batch(db, batch)
    used = held = 0
    for row in db.execute('SELECT paper, edition FROM wear_papers WHERE batch = ? ORDER BY rowid',
                          (batch,)):
        edition = read_frozen_edition(db, row['edition'])
        steps, released = _read_verified(db, row['paper'])
        used += _plate_count(steps, record.plate)
        if released:
            continue
        match = match_prefix(edition.sequences, steps)
        remaining = [_plate_count(sequence[len(steps):], record.plate) for sequence in match.compatible]
        held += max(remaining, default=0)
    return {'batch': record.batch, 'plate': record.plate, 'total': record.total,
            'used': used, 'held': held, 'free': record.total - used - held}
