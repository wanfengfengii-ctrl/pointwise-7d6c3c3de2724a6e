import json
from dataclasses import asdict, dataclass

from bench.occupancy import read_active_mount
from press.progress import match_sheet_to_edition
from press.sheets import find_sheet, list_impressions, set_adopted_edition
from proof.steps import PrintStep, parse_step
from runtime import Problem, encode


SCHEMA = '''CREATE TABLE IF NOT EXISTS adoption_decisions (
    paper TEXT NOT NULL, request_id TEXT NOT NULL, body TEXT NOT NULL,
    PRIMARY KEY(paper, request_id)
)'''


@dataclass(frozen=True)
class AdoptionDecision:
    paper: str
    request_id: str
    original: str
    candidate: str
    status: str
    edition: str
    adoption_id: str | None
    prefix: tuple[PrintStep, ...]
    reason: str | None


def read_adoption_decision(db, paper, request_id):
    row = db.execute('SELECT body FROM adoption_decisions WHERE paper = ? AND request_id = ?',
                     (paper, request_id)).fetchone()
    if row is None:
        return None
    value = json.loads(row['body'])
    value['prefix'] = tuple(parse_step(step) for step in value['prefix'])
    return AdoptionDecision(**value)


def decide_adoption(db, request, candidate):
    paper = request['paper']
    request_id = request['request_id']
    original = request['original']
    old = read_adoption_decision(db, paper, request_id)
    if old is not None:
        if (old.original, old.candidate) != (original, candidate.edition):
            raise Problem('amendment_conflict', 'The press request was already used with other parameters')
        return old
    sheet = find_sheet(db, paper)
    edition, adoption_id = (original, None) if sheet is None else (sheet.edition, sheet.adoption_id)
    if edition != original:
        raise Problem('wrong_original', 'The authorized original does not match the current press edition')
    mount = read_active_mount(db)
    impressions = list_impressions(db, paper)
    status = 'incompatible'
    if sheet is None or mount is None or mount.mount_id != sheet.mount_id:
        reason = 'not_in_production'
    elif not match_sheet_to_edition(impressions, candidate).compatible:
        reason = 'prefix_incompatible'
    else:
        sheet = set_adopted_edition(db, paper, candidate, request_id)
        edition, adoption_id = sheet.edition, sheet.adoption_id
        status, reason = 'adopted', None
    decision = AdoptionDecision(paper, request_id, original, candidate.edition, status, edition,
                                adoption_id, tuple(item.step for item in impressions), reason)
    db.execute('INSERT INTO adoption_decisions VALUES (?, ?, ?)', (paper, request_id, encode(asdict(decision))))
    return decision
