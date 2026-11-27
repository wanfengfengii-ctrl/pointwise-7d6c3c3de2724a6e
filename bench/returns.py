from dataclasses import dataclass

from bench.intake import read_arrival
from bench.occupancy import list_mounts
from runtime import Problem


SCHEMA = '''CREATE TABLE IF NOT EXISTS returned_arrivals (
    paper TEXT PRIMARY KEY REFERENCES arrivals(paper), return_id TEXT NOT NULL UNIQUE
)'''


@dataclass(frozen=True)
class ReturnRecord:
    paper: str
    return_id: str


def read_return(db, paper):
    row = db.execute('SELECT * FROM returned_arrivals WHERE paper = ?', (paper,)).fetchone()
    return None if row is None else ReturnRecord(**row)


def return_arrival(db, paper):
    arrival = read_arrival(db, paper)
    old = read_return(db, paper)
    if old is not None:
        return old
    if arrival.state != 'waiting' or list_mounts(db, paper):
        raise Problem('not_returnable', 'Only a paper that has never been mounted can be returned')
    receipt = ReturnRecord(paper, f'return:{paper}')
    db.execute('INSERT INTO returned_arrivals VALUES (?, ?)', (paper, receipt.return_id))
    db.execute("UPDATE arrivals SET state = 'returned' WHERE paper = ?", (paper,))
    return receipt
