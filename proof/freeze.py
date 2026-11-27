import json
from dataclasses import dataclass

from proof.layouts import read_layout
from proof.sequences import validate_sequences
from proof.steps import PrintStep, parse_sequences, sequence_payload
from runtime import Problem, encode, text


SCHEMA = '''CREATE TABLE IF NOT EXISTS editions (
    edition TEXT PRIMARY KEY, layout TEXT NOT NULL, sequences TEXT NOT NULL
)'''


@dataclass(frozen=True)
class FrozenEdition:
    edition: str
    layout: str
    sequences: tuple[tuple[PrintStep, ...], ...]


def edition_payload(value):
    return {'edition': value.edition, 'layout': value.layout,
            'sequences': sequence_payload(value.sequences)}


def decode_edition(value):
    return FrozenEdition(value['edition'], value['layout'], parse_sequences(value['sequences']))


def freeze_edition(db, layout, edition):
    edition = text(edition, 'edition')
    draft = read_layout(db, layout)
    frozen = FrozenEdition(edition, layout, validate_sequences(db, draft))
    existing = _find(db, edition)
    if existing is not None:
        if existing != frozen:
            raise Problem('edition_conflict', 'This number already names a different fixed edition')
        return existing
    db.execute('INSERT INTO editions VALUES (?, ?, ?)',
               (edition, layout, encode(sequence_payload(frozen.sequences))))
    return frozen


def _find(db, edition):
    row = db.execute('SELECT * FROM editions WHERE edition = ?', (edition,)).fetchone()
    if row is None:
        return None
    return FrozenEdition(row['edition'], row['layout'], parse_sequences(json.loads(row['sequences'])))


def read_frozen_edition(db, edition):
    frozen = _find(db, edition)
    if frozen is None:
        raise Problem('unknown_edition', f'No frozen edition {edition}', 404)
    return frozen
