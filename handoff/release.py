import json
from dataclasses import asdict, dataclass

from handoff.completion import require_ready_for_release
from handoff.provenance import PieceSource, build_provenance
from proof.steps import PrintStep, parse_step
from runtime import Problem, encode


SCHEMA = '''CREATE TABLE IF NOT EXISTS pieces (
    piece_id TEXT PRIMARY KEY, paper TEXT NOT NULL UNIQUE REFERENCES sheets(paper), body TEXT NOT NULL
)'''


@dataclass(frozen=True)
class FinishedPiece:
    piece_id: str
    paper: str
    edition: str
    mount_id: str
    sequence: tuple[PrintStep, ...]
    sources: tuple[PieceSource, ...]


def release_piece(db, paper):
    existing = db.execute('SELECT piece_id FROM pieces WHERE paper = ?', (paper,)).fetchone()
    if existing is not None:
        return read_frozen_piece(db, existing['piece_id'])
    ready = require_ready_for_release(db, paper)
    progress = ready.progress
    sources = build_provenance(db, progress.impressions)
    piece = FinishedPiece(f'piece:{paper}', paper, progress.sheet.edition, progress.sheet.mount_id,
                          tuple(impression.step for impression in progress.impressions), sources)
    db.execute('INSERT INTO pieces VALUES (?, ?, ?)', (piece.piece_id, paper, encode(asdict(piece))))
    return piece


def read_frozen_piece(db, piece_id):
    row = db.execute('SELECT body FROM pieces WHERE piece_id = ?', (piece_id,)).fetchone()
    if row is None:
        raise Problem('unknown_piece', f'No finished piece {piece_id}', 404)
    value = json.loads(row['body'])
    value['sequence'] = tuple(parse_step(step) for step in value['sequence'])
    value['sources'] = tuple(PieceSource(**{**source, 'step': parse_step(source['step'])})
                             for source in value['sources'])
    return FinishedPiece(**value)
