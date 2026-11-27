"""Loaded wear manifests on the press side.

A loaded manifest records that a batch paper has been matched to its label and
bound to a fixed set of official tickets.  Once loaded, those tickets can be
pressed while the issue service is offline, because every ticket datum needed to
verify eligibility is stored locally.

The press also remembers which arrivals are batch papers so that ``mount`` can
refuse a batch paper that was never loaded.
"""

import json
from dataclasses import dataclass

from bench.returns import read_return
from bench.unmount import read_unmount
from press.sheets import list_impressions
from proof.steps import PrintStep, parse_step, step_payload
from runtime import Problem, array, encode, positive


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS wear_members (
        paper TEXT PRIMARY KEY, batch TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS wear_loads (
        paper TEXT PRIMARY KEY, batch TEXT NOT NULL, ticket_ids TEXT NOT NULL
    )''',
    '''CREATE TABLE IF NOT EXISTS wear_tickets (
        ticket_id INTEGER PRIMARY KEY, paper TEXT NOT NULL, batch TEXT NOT NULL,
        edition TEXT NOT NULL, adoption_id TEXT, position INTEGER NOT NULL,
        plate TEXT NOT NULL, placement TEXT NOT NULL
    )''',
)


@dataclass(frozen=True)
class WearLoad:
    paper: str
    batch: str
    ticket_ids: tuple[int, ...]


@dataclass(frozen=True)
class StoredTicket:
    ticket_id: int
    paper: str
    edition: str
    adoption_id: str | None
    position: int
    step: PrintStep


def remember_member(db, paper, batch):
    db.execute('INSERT INTO wear_members VALUES (?, ?) ON CONFLICT(paper) DO NOTHING', (paper, batch))


def member(db, paper):
    row = db.execute('SELECT batch FROM wear_members WHERE paper = ?', (paper,)).fetchone()
    return None if row is None else row['batch']


def read_load(db, paper):
    row = db.execute('SELECT * FROM wear_loads WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        return None
    return WearLoad(row['paper'], row['batch'], tuple(json.loads(row['ticket_ids'])))


def require_load(db, paper):
    load = read_load(db, paper)
    if load is None:
        raise Problem('not_loaded', f'Paper {paper} is not loaded into a wear batch', 409)
    return load


def request_tickets(data):
    values = array(data.get('ticket_ids'), 'ticket_ids')
    if not values:
        raise Problem('invalid_input', 'ticket_ids must contain at least one ticket', 400)
    if len(set(values)) != len(values):
        raise Problem('invalid_input', 'ticket_ids must be unique', 400)
    return tuple(positive(value, 'ticket_id') for value in values)


def load_manifest(db, batch, paper, tickets):
    ids = tuple(sorted(ticket['ticket_id'] for ticket in tickets))
    old = read_load(db, paper)
    if old is not None:
        if old.batch != batch or old.ticket_ids != ids:
            raise Problem('load_conflict', 'This paper is already loaded with other tickets', 409)
        return {'batch': batch, 'paper': paper, 'ticket_ids': list(ids)}
    for ticket in tickets:
        if ticket['paper'] != paper:
            raise Problem('wrong_paper', 'A loaded ticket belongs to a different paper', 409)
        step = parse_step(ticket['step'])
        db.execute('INSERT INTO wear_tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                   (ticket['ticket_id'], paper, batch, ticket['edition'], ticket['adoption_id'],
                    ticket['position'], step.plate, step.placement))
    remember_member(db, paper, batch)
    db.execute('INSERT INTO wear_loads VALUES (?, ?, ?)', (paper, batch, encode(list(ids))))
    return {'batch': batch, 'paper': paper, 'ticket_ids': list(ids)}


def stored_ticket(db, paper, ticket_id):
    row = db.execute('SELECT * FROM wear_tickets WHERE ticket_id = ? AND paper = ?',
                     (ticket_id, paper)).fetchone()
    if row is None:
        return None
    return StoredTicket(row['ticket_id'], row['paper'], row['edition'], row['adoption_id'],
                        row['position'], PrintStep(row['plate'], row['placement']))


def press_state(db, batch, paper):
    """Read the paper's ledger as one atomic snapshot for reconciliation.

    ``released`` is true once the paper has left the bench by either ending: a
    first-time return before mounting, or an unmount after printing.  Steps and
    the release flag are always read together so a snapshot can never pair an
    impressions list from one moment with a release from another.

    A paper that the press has not yet taken in simply reports an empty,
    unreleased snapshot; reconciliation before arrival therefore leaves the
    issue ledger unchanged.
    """
    member_batch = member(db, paper)
    if member_batch is None:
        load = read_load(db, paper)
        member_batch = None if load is None else load.batch
    if member_batch is not None and member_batch != batch:
        raise Problem('state_conflict', 'The paper belongs to another batch', 409)
    row = db.execute('SELECT 1 FROM arrivals WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        return {'batch': batch, 'paper': paper, 'steps': [], 'released': False}
    steps = [impression.step for impression in list_impressions(db, paper)]
    released = read_return(db, paper) is not None or read_unmount(db, paper) is not None
    return {'batch': batch, 'paper': paper,
            'steps': [step_payload(step) for step in steps], 'released': released}
