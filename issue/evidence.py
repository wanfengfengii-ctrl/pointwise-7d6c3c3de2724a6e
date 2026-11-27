from dataclasses import dataclass

from issue.orders import read_order
from proof.steps import PrintStep, parse_step
from runtime import Problem


SCHEMA = '''CREATE TABLE IF NOT EXISTS received_receipts (
    ticket_id INTEGER PRIMARY KEY REFERENCES tickets(ticket_id),
    paper TEXT NOT NULL REFERENCES orders(paper), position INTEGER NOT NULL,
    receipt_id TEXT NOT NULL UNIQUE, edition TEXT NOT NULL,
    plate TEXT NOT NULL, placement TEXT NOT NULL, mount_id TEXT NOT NULL,
    UNIQUE(paper, position)
)'''


@dataclass(frozen=True)
class ReceivedReceipt:
    ticket_id: int
    paper: str
    position: int
    receipt_id: str
    edition: str
    step: PrintStep
    mount_id: str


def _receipt(row):
    return ReceivedReceipt(row['ticket_id'], row['paper'], row['position'], row['receipt_id'],
                           row['edition'], PrintStep(row['plate'], row['placement']), row['mount_id'])


def record_received_receipt(db, ticket, value):
    receipt = ReceivedReceipt(value['ticket_id'], value['paper'], value['position'], value['receipt_id'],
                              value['edition'], parse_step(value['step']), value['mount_id'])
    received = (receipt.ticket_id, receipt.paper, receipt.position, receipt.edition, receipt.step)
    issued = (ticket.ticket_id, ticket.paper, ticket.position, ticket.edition, ticket.step)
    if received != issued:
        raise Problem('receipt_conflict', 'The press receipt does not match the official ticket')
    old = db.execute('SELECT * FROM received_receipts WHERE ticket_id = ? OR (paper = ? AND position = ?)',
                     (receipt.ticket_id, receipt.paper, receipt.position)).fetchone()
    if old is not None:
        if _receipt(old) != receipt:
            raise Problem('receipt_conflict', 'A different receipt is already filed')
        return receipt
    db.execute('INSERT INTO received_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
               (receipt.ticket_id, receipt.paper, receipt.position, receipt.receipt_id,
                receipt.edition, receipt.step.plate, receipt.step.placement, receipt.mount_id))
    return receipt


def list_received_receipts(db, paper):
    read_order(db, paper)
    rows = db.execute('SELECT * FROM received_receipts WHERE paper = ? ORDER BY position', (paper,))
    return [_receipt(row) for row in rows]
