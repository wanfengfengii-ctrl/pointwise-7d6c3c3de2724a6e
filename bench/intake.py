from dataclasses import dataclass

from runtime import Problem


SCHEMA = '''CREATE TABLE IF NOT EXISTS arrivals (
    paper TEXT PRIMARY KEY, original TEXT NOT NULL REFERENCES press_editions(edition),
    state TEXT NOT NULL CHECK(state IN ('waiting', 'mounted', 'removed', 'returned'))
)'''


@dataclass(frozen=True)
class IntakeRecord:
    paper: str
    original: str
    state: str


def register_arrival(db, paper, label, order):
    if paper != label or order['paper'] != paper or order['original'] != order['edition']['edition']:
        raise Problem('wrong_paper', 'The arrival label does not match the formal order')
    original = order['original']
    db.execute('''INSERT INTO arrivals VALUES (?, ?, 'waiting')
                  ON CONFLICT(paper) DO NOTHING''', (paper, original))
    arrival = read_arrival(db, paper)
    if arrival.original != original:
        raise Problem('arrival_conflict', 'The arrival is already bound to another fixed edition')
    return arrival


def read_arrival(db, paper):
    row = db.execute('SELECT * FROM arrivals WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        raise Problem('unknown_arrival', f'Paper {paper} has not arrived', 404)
    return IntakeRecord(**row)
