from dataclasses import dataclass

from bench.occupancy import require_active_mount
from runtime import Problem


SCHEMA = '''CREATE TABLE IF NOT EXISTS unmounts (
    paper TEXT PRIMARY KEY REFERENCES arrivals(paper),
    mount_id TEXT NOT NULL UNIQUE REFERENCES mounts(mount_id)
)'''


@dataclass(frozen=True)
class UnmountRecord:
    paper: str
    mount_id: str


def read_unmount(db, paper):
    row = db.execute('SELECT * FROM unmounts WHERE paper = ?', (paper,)).fetchone()
    return None if row is None else UnmountRecord(**row)


def unmount_sheet(db, paper, mount_id):
    old = read_unmount(db, paper)
    if old is not None:
        if old.mount_id != mount_id:
            raise Problem('wrong_mount', 'The paper was removed from a different mount')
        return old
    require_active_mount(db, paper, mount_id)
    db.execute('UPDATE mounts SET active = 0 WHERE mount_id = ?', (mount_id,))
    db.execute("UPDATE arrivals SET state = 'removed' WHERE paper = ?", (paper,))
    db.execute('INSERT INTO unmounts VALUES (?, ?)', (paper, mount_id))
    return UnmountRecord(paper, mount_id)
