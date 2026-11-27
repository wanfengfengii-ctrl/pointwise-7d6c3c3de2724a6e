from dataclasses import dataclass

from issue.lookup import has_pending_request, read_confirmed_edition
from proof.freeze import read_frozen_edition
from proof.sequences import contains_ticket_step
from proof.steps import PrintStep, parse_step
from runtime import Problem, positive


SCHEMA = '''CREATE TABLE IF NOT EXISTS tickets (
    ticket_id INTEGER PRIMARY KEY, paper TEXT NOT NULL REFERENCES orders(paper),
    edition TEXT NOT NULL REFERENCES editions(edition), adoption_id TEXT,
    position INTEGER NOT NULL, plate TEXT NOT NULL, placement TEXT NOT NULL
)'''


@dataclass(frozen=True)
class PrintTicket:
    ticket_id: int
    paper: str
    edition: str
    adoption_id: str | None
    position: int
    step: PrintStep


def issue_ticket(db, paper, position, step):
    position = positive(position, 'position')
    edition, adoption_id = read_confirmed_edition(db, paper)
    if has_pending_request(db, paper):
        raise Problem('amendment_pending', 'Confirm the amendment before issuing another ticket')
    frozen = read_frozen_edition(db, edition)
    if not contains_ticket_step(frozen.sequences, position, step):
        raise Problem('step_not_in_edition', 'The fixed edition has no such step at that position')
    cursor = db.execute('''INSERT INTO tickets (paper, edition, adoption_id, position, plate, placement)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (paper, edition, adoption_id, position, step.plate, step.placement))
    return read_ticket(db, cursor.lastrowid)


def decode_ticket(value):
    return PrintTicket(value['ticket_id'], value['paper'], value['edition'], value['adoption_id'],
                       value['position'], parse_step(value['step']))


def read_ticket(db, ticket_id):
    row = db.execute('SELECT * FROM tickets WHERE ticket_id = ?', (ticket_id,)).fetchone()
    if row is None:
        raise Problem('unknown_ticket', f'No formal ticket {ticket_id}', 404)
    return PrintTicket(row['ticket_id'], row['paper'], row['edition'], row['adoption_id'],
                       row['position'], PrintStep(row['plate'], row['placement']))
