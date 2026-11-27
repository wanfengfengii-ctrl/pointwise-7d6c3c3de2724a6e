from dataclasses import dataclass

from proof.freeze import read_frozen_edition
from runtime import Problem, text


SCHEMA = '''CREATE TABLE IF NOT EXISTS orders (
    paper TEXT PRIMARY KEY, original TEXT NOT NULL REFERENCES editions(edition)
)'''


@dataclass(frozen=True)
class JobOrder:
    paper: str
    original: str


def issue_order(db, paper, edition):
    paper = text(paper, 'paper')
    read_frozen_edition(db, edition)
    db.execute('INSERT INTO orders VALUES (?, ?) ON CONFLICT(paper) DO NOTHING', (paper, edition))
    order = read_order(db, paper)
    if order.original != edition:
        raise Problem('order_conflict', 'Paper is already issued under a different original edition')
    return order


def read_order(db, paper):
    row = db.execute('SELECT * FROM orders WHERE paper = ?', (paper,)).fetchone()
    if row is None:
        raise Problem('unknown_order', f'No order for paper {paper}', 404)
    return JobOrder(**row)
