from bench.intake import read_arrival
from bench.occupancy import list_mounts, read_active_mount, require_active_mount
from runtime import Problem


def mount_sheet(db, paper, mount_id):
    arrival = read_arrival(db, paper)
    mounts = list_mounts(db, paper)
    if mounts and mounts[0].active:
        return require_active_mount(db, paper, mount_id)
    if arrival.state != 'waiting':
        raise Problem('not_mountable', 'Only a waiting arrival can be mounted')
    if read_active_mount(db) is not None:
        raise Problem('bench_occupied', 'Another paper is already on the bench')
    if db.execute('SELECT 1 FROM mounts WHERE mount_id = ?', (mount_id,)).fetchone():
        raise Problem('mount_conflict', 'This mount number was already used')
    db.execute('INSERT INTO mounts VALUES (?, ?, 1)', (mount_id, paper))
    db.execute("UPDATE arrivals SET state = 'mounted' WHERE paper = ?", (paper,))
    return require_active_mount(db, paper, mount_id)
