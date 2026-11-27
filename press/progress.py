from dataclasses import dataclass

from press.sheets import ImpressionRecord, PhysicalSheet, list_impressions, read_sheet, read_sheet_edition
from proof.sequences import SequenceMatch, match_prefix


@dataclass(frozen=True)
class SheetProgress:
    sheet: PhysicalSheet
    impressions: tuple[ImpressionRecord, ...]
    match: SequenceMatch


def match_sheet_to_edition(impressions, edition):
    return match_prefix(edition.sequences, (impression.step for impression in impressions))


def read_progress(db, paper):
    sheet = read_sheet(db, paper)
    edition = read_sheet_edition(db, sheet.edition)
    impressions = list_impressions(db, paper)
    return SheetProgress(sheet, impressions, match_sheet_to_edition(impressions, edition))
