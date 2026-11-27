from dataclasses import dataclass

from bench.unmount import UnmountRecord, read_unmount
from press.progress import SheetProgress, read_progress
from runtime import Problem


@dataclass(frozen=True)
class CompletionCheck:
    progress: SheetProgress
    unmount: UnmountRecord | None


def check_completion(db, paper):
    progress = read_progress(db, paper)
    if not progress.match.complete:
        raise Problem('incomplete', 'Actual impressions do not equal a complete edition alternative')
    return CompletionCheck(progress, read_unmount(db, paper))


def require_ready_for_release(db, paper):
    completion = check_completion(db, paper)
    if completion.unmount is None or completion.unmount.mount_id != completion.progress.sheet.mount_id:
        raise Problem('not_unmounted', 'The completed paper has not been removed from its press mount')
    return completion
