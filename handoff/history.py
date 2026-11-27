from dataclasses import dataclass

from handoff.release import read_frozen_piece


SCHEMA = '''CREATE TABLE IF NOT EXISTS pickups (
    pickup_id INTEGER PRIMARY KEY, piece_id TEXT NOT NULL REFERENCES pieces(piece_id)
)'''


@dataclass(frozen=True)
class PickupRecord:
    pickup_id: int
    piece_id: str


def pickup_piece(db, piece_id):
    piece = read_frozen_piece(db, piece_id)
    db.execute('INSERT INTO pickups (piece_id) VALUES (?)', (piece_id,))
    return piece


def list_pickups(db, piece_id):
    read_frozen_piece(db, piece_id)
    rows = db.execute('SELECT * FROM pickups WHERE piece_id = ? ORDER BY pickup_id', (piece_id,))
    return [PickupRecord(**row) for row in rows]
