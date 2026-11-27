from dataclasses import dataclass

from press.receipts import find_receipt
from proof.steps import PrintStep
from runtime import Problem


@dataclass(frozen=True)
class PieceSource:
    position: int
    step: PrintStep
    edition: str
    ticket_id: int
    receipt_id: str
    mount_id: str


def build_provenance(db, impressions):
    sources = []
    for impression in impressions:
        receipt = find_receipt(db, impression.paper, impression.ticket_id)
        if receipt is None:
            raise Problem('missing_receipt', f'Impression {impression.position} has no original receipt')
        sources.append(PieceSource(receipt.position, receipt.step, receipt.edition, receipt.ticket_id,
                                   receipt.receipt_id, receipt.mount_id))
    return tuple(sources)
