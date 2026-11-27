from dataclasses import dataclass

from runtime import Problem, text


SCHEMA = '''CREATE TABLE IF NOT EXISTS plates (
    plate TEXT PRIMARY KEY, name TEXT NOT NULL
)'''


@dataclass(frozen=True)
class Plate:
    plate: str
    name: str


def register_plate(db, plate, name):
    item = Plate(text(plate, 'plate'), text(name, 'name'))
    db.execute('''INSERT INTO plates (plate, name) VALUES (?, ?)
                  ON CONFLICT(plate) DO UPDATE SET name = excluded.name''',
               (item.plate, item.name))
    return item


def require_plate(db, plate):
    row = db.execute('SELECT plate, name FROM plates WHERE plate = ?', (plate,)).fetchone()
    if row is None:
        raise Problem('unknown_plate', f'Plate {plate} is not registered', 400)
    return Plate(**row)
