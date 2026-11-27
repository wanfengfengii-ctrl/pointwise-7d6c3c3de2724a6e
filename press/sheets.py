import json
from dataclasses import dataclass

from proof.freeze import decode_edition, edition_payload
from proof.steps import PrintStep
from runtime import Problem, encode


SCHEMA = (
    'CREATE TABLE IF NOT EXISTS press_editions (edition TEXT PRIMARY KEY, snapshot TEXT NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS sheets (
        paper TEXT PRIMARY KEY REFERENCES arrivals(paper),
        mount_id TEXT NOT NULL UNIQUE REFERENCES mounts(mount_id),
        edition TEXT NOT NULL REFERENCES press_editions(edition), adoption_id TEXT
    )''',
    '''CREATE TABLE IF NOT EXISTS impressions (
        paper TEXT NOT NULL REFERENCES sheets(paper), position INTEGER NOT NULL,
        plate TEXT NOT NULL, placement TEXT NOT NULL, edition TEXT NOT NULL REFERENCES press_editions(edition),
        ticket_id INTEGER NOT NULL UNIQUE, mount_id TEXT NOT NULL REFERENCES mounts(mount_id),
        PRIMARY KEY(paper, position)
    )''',
)


@dataclass(frozen=True)
class PhysicalSheet:
    paper: str
    mount_id: str
    edition: str
    adoption_id: str | None


@dataclass(frozen=True)
class ImpressionRecord:
    paper: str
    position: int
    step: PrintStep
    edition: str
    ticket_id: int
    mount_id: str


def remember_edition(db, edition):
    snapshot = encode(edition_payload(edition))
    db.execute('INSERT INTO press_editions VALUES (?, ?) ON CONFLICT(edition) DO NOTHING',
               (edition.edition, snapshot))
    if read_sheet_edition(db, edition.edition) != edition:
        raise Problem('edition_conflict', 'The press already has different content for this edition')


def read_sheet_edition(db, edition):
    row = db.execute('SELECT snapshot FROM press_editions WHERE edition = ?', (edition,)).fetchone()
    if row is None:
        raise Problem('unknown_edition', f'No edition {edition} in the press ledger', 404)
    return decode_edition(json.loads(row['snapshot']))


def open_sheet(db, mount, original):
    db.execute('''INSERT INTO sheets VALUES (?, ?, ?, NULL)
                  ON CONFLICT(paper) DO NOTHING''', (mount.paper, mount.mount_id, original))
    sheet = read_sheet(db, mount.paper)
    if sheet.mount_id != mount.mount_id:
        raise Problem('wrong_mount', 'The paper has a different mount in the press ledger')
    return sheet


def find_sheet(db, paper):
    row = db.execute('SELECT * FROM sheets WHERE paper = ?', (paper,)).fetchone()
    return None if row is None else PhysicalSheet(**row)


def read_sheet(db, paper):
    sheet = find_sheet(db, paper)
    if sheet is None:
        raise Problem('unknown_sheet', f'Paper {paper} has no press ledger', 404)
    return sheet


def set_adopted_edition(db, paper, edition, adoption_id):
    remember_edition(db, edition)
    db.execute('UPDATE sheets SET edition = ?, adoption_id = ? WHERE paper = ?',
               (edition.edition, adoption_id, paper))
    return read_sheet(db, paper)


def impression_from_row(row):
    return ImpressionRecord(row['paper'], row['position'], PrintStep(row['plate'], row['placement']),
                            row['edition'], row['ticket_id'], row['mount_id'])


def list_impressions(db, paper):
    rows = db.execute('SELECT * FROM impressions WHERE paper = ? ORDER BY position', (paper,))
    return tuple(impression_from_row(row) for row in rows)
