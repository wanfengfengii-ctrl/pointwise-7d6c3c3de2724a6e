import json
from dataclasses import dataclass

from proof.plates import require_plate
from proof.steps import PrintStep, parse_sequences, parse_step, sequence_payload, step_payload
from runtime import Problem, array, encode, text


SCHEMA = '''CREATE TABLE IF NOT EXISTS layouts (
    layout TEXT PRIMARY KEY, placements TEXT NOT NULL, sequences TEXT NOT NULL
)'''


@dataclass(frozen=True)
class WorkingLayout:
    layout: str
    placements: tuple[PrintStep, ...]
    sequences: tuple[tuple[PrintStep, ...], ...]


def save_layout(db, layout, placements, sequences):
    layout = text(layout, 'layout')
    allowed = tuple(parse_step(step) for step in array(placements, 'placements'))
    if len(set(allowed)) != len(allowed):
        raise Problem('duplicate_placement', 'A plate and placement pair was listed twice', 400)
    for step in allowed:
        require_plate(db, step.plate)
    draft = WorkingLayout(layout, allowed, parse_sequences(sequences))
    db.execute('''INSERT INTO layouts VALUES (?, ?, ?)
                  ON CONFLICT(layout) DO UPDATE SET placements = excluded.placements,
                  sequences = excluded.sequences''',
               (layout, encode([step_payload(step) for step in allowed]),
                encode(sequence_payload(draft.sequences))))
    return draft


def read_layout(db, layout):
    row = db.execute('SELECT * FROM layouts WHERE layout = ?', (layout,)).fetchone()
    if row is None:
        raise Problem('unknown_layout', f'No working layout {layout}', 404)
    return WorkingLayout(layout, tuple(parse_step(step) for step in json.loads(row['placements'])),
                         parse_sequences(json.loads(row['sequences'])))


def require_placement(db, layout, step):
    require_plate(db, step.plate)
    if step not in layout.placements:
        raise Problem('unknown_placement',
                      f'{step.plate} cannot use placement {step.placement} in {layout.layout}', 400)
