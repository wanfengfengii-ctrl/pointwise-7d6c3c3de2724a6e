from bench.occupancy import require_active_mount
from press.progress import read_progress
from press.receipts import find_receipt, store_receipt
from press.sheets import ImpressionRecord
from runtime import Problem


def submit_impression(db, paper, ticket):
    if ticket.paper != paper:
        raise Problem('wrong_paper', 'The original ticket belongs to a different paper')
    old = find_receipt(db, paper, ticket.ticket_id)
    if old is not None:
        return old
    mount = require_active_mount(db, paper)
    progress = read_progress(db, paper)
    sheet = progress.sheet
    if mount.mount_id != sheet.mount_id:
        raise Problem('wrong_mount', 'The active mount does not match the press ledger')
    if (ticket.edition, ticket.adoption_id) != (sheet.edition, sheet.adoption_id):
        raise Problem('stale_ticket', 'This ticket has lost eligibility for a first impression')
    position = len(progress.impressions) + 1
    if ticket.position != position or ticket.step not in progress.match.next_steps:
        raise Problem('out_of_order', 'The ticket cannot extend the actual prefix at the next position')
    record = ImpressionRecord(paper, position, ticket.step, sheet.edition, ticket.ticket_id, mount.mount_id)
    db.execute('INSERT INTO impressions VALUES (?, ?, ?, ?, ?, ?, ?)',
               (paper, position, record.step.plate, record.step.placement,
                record.edition, record.ticket_id, record.mount_id))
    return store_receipt(db, record)
