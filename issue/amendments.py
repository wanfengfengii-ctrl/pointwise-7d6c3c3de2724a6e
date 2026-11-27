from dataclasses import dataclass

from issue import wear
from issue.lookup import register_request, save_decision
from proof.freeze import read_frozen_edition
from runtime import Problem, text


@dataclass(frozen=True)
class AmendmentRequest:
    paper: str
    original: str
    candidate: str
    request_id: str


def submit_amendment(db, data):
    request = AmendmentRequest(*(text(data.get(key), key)
                                 for key in ('paper', 'original', 'candidate', 'request_id')))
    read_frozen_edition(db, request.original)
    read_frozen_edition(db, request.candidate)
    if request.original == request.candidate:
        raise Problem('same_edition', 'An amendment requires a different fixed edition', 400)
    if wear.is_batch_paper(db, request.paper):
        raise Problem('batch_paper_fixed', 'A batch paper keeps its signed edition', 409)
    wear.reject_reserved_edition(db, request.candidate)
    return register_request(db, request)


def record_known_decision(db, record, decision):
    return save_decision(db, record, decision)
