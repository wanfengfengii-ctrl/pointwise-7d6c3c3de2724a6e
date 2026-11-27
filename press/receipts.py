from dataclasses import dataclass

from press.sheets import impression_from_row
from proof.steps import PrintStep


SCHEMA = '''CREATE TABLE IF NOT EXISTS receipts (
    receipt_id TEXT PRIMARY KEY, paper TEXT NOT NULL, position INTEGER NOT NULL,
    UNIQUE(paper, position), FOREIGN KEY(paper, position) REFERENCES impressions(paper, position)
)'''


@dataclass(frozen=True)
class PressReceipt:
    receipt_id: str
    paper: str
    position: int
    step: PrintStep
    edition: str
    ticket_id: int
    mount_id: str


def _receipt(receipt_id, impression):
    return PressReceipt(receipt_id, impression.paper, impression.position, impression.step,
                        impression.edition, impression.ticket_id, impression.mount_id)


def store_receipt(db, impression):
    receipt_id = f'R{impression.ticket_id}'
    db.execute('INSERT INTO receipts VALUES (?, ?, ?)', (receipt_id, impression.paper, impression.position))
    return _receipt(receipt_id, impression)


def find_receipt(db, paper, ticket_id):
    row = db.execute('''SELECT i.*, r.receipt_id FROM impressions AS i
                        JOIN receipts AS r ON r.paper = i.paper AND r.position = i.position
                        WHERE i.paper = ? AND i.ticket_id = ?''', (paper, ticket_id)).fetchone()
    return None if row is None else _receipt(row['receipt_id'], impression_from_row(row))
