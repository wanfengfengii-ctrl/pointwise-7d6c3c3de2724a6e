from dataclasses import dataclass

from runtime import Problem


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS mounts (
        mount_id TEXT PRIMARY KEY, paper TEXT NOT NULL UNIQUE REFERENCES arrivals(paper),
        active INTEGER NOT NULL CHECK(active IN (0, 1))
    )''',
    'CREATE UNIQUE INDEX IF NOT EXISTS one_active_mount ON mounts(active) WHERE active = 1',
)


@dataclass(frozen=True)
class MountRecord:
    mount_id: str
    paper: str
    active: bool


def _mount(row):
    return MountRecord(row['mount_id'], row['paper'], bool(row['active']))


def read_active_mount(db):
    row = db.execute('SELECT * FROM mounts WHERE active = 1').fetchone()
    return None if row is None else _mount(row)


def require_active_mount(db, paper, mount_id=None):
    mount = read_active_mount(db)
    if mount is None or mount.paper != paper:
        raise Problem('wrong_paper', 'This paper is not on the bench')
    if mount_id is not None and mount.mount_id != mount_id:
        raise Problem('wrong_mount', 'The stated mount is not the active mount')
    return mount


def list_mounts(db, paper):
    return [_mount(row) for row in db.execute('SELECT * FROM mounts WHERE paper = ? ORDER BY rowid', (paper,))]
