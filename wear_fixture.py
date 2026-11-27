import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from day import arrive, finish, mount, step, steps, ticket
from issue.service import IssueService
from press.service import PressService
from runtime import Problem, Unavailable, encode, invoke, make_server, running


class Link:
    def __init__(self):
        self.service = None
        self.hook = None

    def dispatch(self, route, data):
        if self.hook is not None:
            return self.hook(self.service.dispatch, route, data)
        return self.service.dispatch(route, data)

    @contextmanager
    def intercept(self, hook):
        previous = self.hook
        self.hook = hook
        try:
            yield
        finally:
            self.hook = previous


def offline(dispatch, route, data):
    raise Unavailable("Fixture: destination unavailable")


def lose_reply(operation):
    def relay(dispatch, route, data):
        result = dispatch(route, data)
        if route == operation:
            raise Unavailable("Fixture: original response lost after dispatch")
        return result
    return relay


class Workshop:
    def __init__(self, root, issue_link, issue_url, press_link, press_url):
        self.root = Path(root)
        self.issue_link = issue_link
        self.issue_url = issue_url
        self.press_link = press_link
        self.press_url = press_url
        self.reopen()

    def reopen(self):
        self.issue_link.service = IssueService(self.root / "issue.sqlite", self.press_url)
        self.press_link.service = PressService(self.root / "press.sqlite", self.issue_url)

    def issue(self, route, **data):
        return invoke(self.issue_url, route, data)

    def press(self, route, **data):
        return invoke(self.press_url, route, data)


@contextmanager
def workshop(root):
    issue_link, press_link = Link(), Link()
    with ExitStack() as stack:
        issue_url = stack.enter_context(running(make_server(issue_link.dispatch)))
        press_url = stack.enter_context(running(make_server(press_link.dispatch)))
        yield Workshop(root, issue_link, issue_url, press_link, press_url)


def seed_plates(work):
    for plate in "ABCD":
        work.issue("plate", plate=plate, name=plate)


def seed_editions(work):
    for edition, alternatives in (("fork", ("ABB", "CB")), ("one", ("B",)), ("edge", ("C", "CB"))):
        work.issue("layout", layout=edition, placements=steps("ABCD"),
                   sequences=[steps(order) for order in alternatives])
        work.issue("freeze", layout=edition, edition=edition)


def wear_open(work, batch, plate, total):
    return work.issue("wear.open", batch=batch, plate=plate, total=total)


def wear_sign(work, batch, paper, edition, request_id):
    return work.issue("wear.issue", batch=batch, paper=paper, edition=edition, request_id=request_id)


def wear_load(work, batch, paper, ticket_ids, label=None):
    return work.press("wear.load", batch=batch, paper=paper, label=paper if label is None else label,
                      ticket_ids=list(ticket_ids))


def wear_reconcile(work, batch, paper):
    return work.issue("wear.reconcile", batch=batch, paper=paper)


def wear_balance(work, batch):
    return work.issue("wear.balance", batch=batch)


def wear_state(work, batch, paper):
    return work.press("wear.state", batch=batch, paper=paper)


def expect_problem(code, operation):
    try:
        operation()
    except Problem as error:
        assert error.code == code, (error.code, code)
        return error
    raise AssertionError(f"Expected a {code} refusal")


def expect_unavailable(operation):
    try:
        operation()
    except Unavailable:
        return
    raise AssertionError("Expected an unavailable response")


def observe_v1(root):
    with workshop(root) as work:
        seed_plates(work)
        seed_editions(work)
        arrive(work, "P", "fork")
        mount(work, "P")
        c = ticket(work, "P", 1, "C")
        b = ticket(work, "P", 2, "B")

        def stamp_c():
            return work.press("press", paper="P", ticket_id=c)

        with work.issue_link.intercept(offline):
            expect_unavailable(stamp_c)
            assert work.press("impressions", paper="P") == []
        q = work.issue("issue", paper="Q", edition="one")
        assert q == {"paper": "Q", "original": "one"}
        with work.press_link.intercept(lose_reply("press")):
            expect_unavailable(stamp_c)
        work.reopen()
        first = work.press("receipt", paper="P", ticket_id=c)
        with work.issue_link.intercept(offline):
            assert stamp_c() == first
        assert len(work.press("impressions", paper="P")) == 1
        assert work.issue("receive", paper="P", ticket_id=c) == first
        r = work.issue("issue", paper="R", edition="one")
        assert r == {"paper": "R", "original": "one"}
        second = work.press("press", paper="P", ticket_id=b)
        piece = finish(work, "P")
        assert piece["sequence"] == steps("CB")
        assert [row["receipt_id"] for row in piece["sources"]] == [first["receipt_id"], second["receipt_id"]]
        work.reopen()
        assert work.press("pickup", piece_id=piece["piece_id"]) == piece
        return {"orders": [q, r], "first_receipt": first, "piece": piece}


def sign_fork(work):
    """Pre-print P's four fork tickets: A1, C1, B2, B3."""
    return (ticket(work, "P", 1, "A"), ticket(work, "P", 1, "C"),
            ticket(work, "P", 2, "B"), ticket(work, "P", 3, "B"))


def observe_v2(root):
    """The full dedicated-plate batch from WEAR.md: signing, reconciliation, and
    two papers sharing B."""
    with workshop(root) as work:
        seed_plates(work)
        seed_editions(work)
        assert wear_open(work, "W", "B", 2) == {"batch": "W", "plate": "B", "total": 2}
        assert wear_open(work, "W", "B", 2) == {"batch": "W", "plate": "B", "total": 2}
        assert wear_sign(work, "W", "P", "fork", "sign-P") == {
            "batch": "W", "paper": "P", "original": "fork", "request_id": "sign-P"}
        a1, c1, b2, b3 = sign_fork(work)
        outside = ticket(work, "P", 1, "C")  # a legal ticket, but never loaded
        expected = sorted([a1, c1, b2, b3])
        assert wear_load(work, "W", "P", [a1, c1, b2, b3]) == {
            "batch": "W", "paper": "P", "ticket_ids": expected}
        assert wear_load(work, "W", "P", [b3, b2, c1, a1]) == {
            "batch": "W", "paper": "P", "ticket_ids": expected}
        expect_problem("load_conflict", lambda: wear_load(work, "W", "P", [a1, c1, b2]))

        arrive(work, "P", "fork")
        mount(work, "P")

        def stamp(ticket_id):
            return work.press("press", paper="P", ticket_id=ticket_id)

        # A long-sequence ticket (B at position 3) cannot open an empty prefix.
        expect_problem("out_of_order", lambda: stamp(b3))

        # Disconnect the issue service and lose the press's business reply on the
        # very first press; the loaded ticket still cuts one C.
        with work.issue_link.intercept(offline), work.press_link.intercept(lose_reply("press")):
            expect_unavailable(lambda: stamp(c1))
        assert [row["step"] for row in work.press("impressions", paper="P")] == steps("C")
        work.reopen()
        first = work.press("receipt", paper="P", ticket_id=c1)
        with work.issue_link.intercept(offline):
            assert stamp(c1) == first
        assert len(work.press("impressions", paper="P")) == 1

        refused_early = expect_problem("insufficient_wear",
                                       lambda: wear_sign(work, "W", "Q", "one", "sign-Q")).code
        expect_problem("insufficient_wear", lambda: wear_sign(work, "W", "R", "one", "sign-R"))
        before = wear_balance(work, "W")
        assert before == {"batch": "W", "plate": "B", "total": 2, "used": 0, "held": 2, "free": 0}
        after_p = wear_reconcile(work, "W", "P")
        assert after_p == {"batch": "W", "plate": "B", "total": 2, "used": 0, "held": 1, "free": 1}

        with work.press_link.intercept(offline):
            assert wear_balance(work, "W") == after_p
            accepted_q = wear_sign(work, "W", "Q", "one", "sign-Q")
            assert accepted_q == {
                "batch": "W", "paper": "Q", "original": "one", "request_id": "sign-Q"}
            expect_problem("insufficient_wear", lambda: wear_sign(work, "W", "R", "one", "sign-R"))
        signed_q = wear_balance(work, "W")
        assert signed_q == {"batch": "W", "plate": "B", "total": 2, "used": 0, "held": 2, "free": 0}

        stale = {"batch": "W", "paper": "P", "steps": [], "released": False}
        with work.press_link.intercept(lambda dispatch, route, data: stale if route == "wear.state"
                                       else dispatch(route, data)):
            assert wear_reconcile(work, "W", "P") == signed_q
        assert work.issue("wear.balance", batch="W") == signed_q

        expect_problem("not_loaded", lambda: work.press("press", paper="P", ticket_id=outside))
        second = work.press("press", paper="P", ticket_id=b2)
        assert second["step"] == steps("B")[0]
        piece_p = finish(work, "P")
        assert piece_p["sequence"] == steps("CB")
        assert [row["ticket_id"] for row in piece_p["sources"]] == [c1, b2]
        assert [row["mount_id"] for row in piece_p["sources"]] == ["mount:P", "mount:P"]

        settled_p = {"batch": "W", "plate": "B", "total": 2, "used": 1, "held": 1, "free": 0}
        assert wear_reconcile(work, "W", "P") == settled_p
        assert wear_reconcile(work, "W", "P") == settled_p

        q_b = ticket(work, "Q", 1, "B")
        assert wear_load(work, "W", "Q", [q_b]) == {"batch": "W", "paper": "Q", "ticket_ids": [q_b]}
        arrive(work, "Q", "one")
        mount(work, "Q")
        qb = work.press("press", paper="Q", ticket_id=q_b)
        piece_q = finish(work, "Q")
        assert piece_q["sequence"] == steps("B")
        assert [row["receipt_id"] for row in piece_q["sources"]] == [qb["receipt_id"]]
        settled = {"batch": "W", "plate": "B", "total": 2, "used": 2, "held": 0, "free": 0}
        assert wear_reconcile(work, "W", "Q") == settled

        impressions_p = work.press("impressions", paper="P")
        impressions_q = work.press("impressions", paper="Q")
        work.reopen()
        recovered_p = work.press("pickup", piece_id=piece_p["piece_id"])
        recovered_q = work.press("pickup", piece_id=piece_q["piece_id"])
        assert recovered_p == piece_p and recovered_q == piece_q
        assert wear_sign(work, "W", "Q", "one", "sign-Q") == {
            "batch": "W", "paper": "Q", "original": "one", "request_id": "sign-Q"}
        assert wear_load(work, "W", "Q", [q_b]) == {"batch": "W", "paper": "Q", "ticket_ids": [q_b]}
        assert work.press("receipt", paper="P", ticket_id=c1) == first
        assert work.issue("wear.balance", batch="W") == settled
    return {"paper_P": piece_p, "paper_Q": piece_q,
            "first_receipt": first, "q_receipt": qb,
            "before": before, "after_p": after_p, "signed_q": signed_q, "settled": settled,
            "refused_early": refused_early, "accepted_q": accepted_q,
            "impressions_p": impressions_p, "impressions_q": impressions_q,
            "recovered_p": recovered_p, "recovered_q": recovered_q}


def observe_edge(root, *, continue_after_c):
    """The `edge` edition [C] or [C,B] under a batch of one.

    A bare C is a complete short sequence, yet the compatible longer sequence
    keeps its continuation alive before the paper is taken off the press.  Both
    branches mint identical receipts; only whether B is pressed differs, and the
    reconciliation must never fuse a pre-B reading with a post-return release.
    """
    with workshop(root) as work:
        seed_plates(work)
        seed_editions(work)
        assert wear_open(work, "E", "B", 1) == {"batch": "E", "plate": "B", "total": 1}
        assert wear_sign(work, "E", "S", "edge", "sign-S") == {
            "batch": "E", "paper": "S", "original": "edge", "request_id": "sign-S"}
        c1 = ticket(work, "S", 1, "C")
        b2 = ticket(work, "S", 2, "B")
        assert wear_load(work, "E", "S", [c1, b2]) == {
            "batch": "E", "paper": "S", "ticket_ids": [c1, b2]}
        arrive(work, "S", "edge")
        mount(work, "S")
        work.press("press", paper="S", ticket_id=c1)
        pre = wear_reconcile(work, "E", "S")
        assert pre == {"batch": "E", "plate": "B", "total": 1, "used": 0, "held": 1, "free": 0}
        if continue_after_c:
            work.press("press", paper="S", ticket_id=b2)
            mid = wear_reconcile(work, "E", "S")
            assert mid == {"batch": "E", "plate": "B", "total": 1, "used": 1, "held": 0, "free": 0}
            piece = finish(work, "S")
            assert piece["sequence"] == steps("CB")
            after = wear_reconcile(work, "E", "S")
            assert after == {"batch": "E", "plate": "B", "total": 1, "used": 1, "held": 0, "free": 0}
        else:
            work.press("stage", action="unmount", paper="S", mount_id="mount:S")
            piece = work.press("release", paper="S")
            assert piece["sequence"] == steps("C")
            after = wear_reconcile(work, "E", "S")
            assert after == {"batch": "E", "plate": "B", "total": 1, "used": 0, "held": 0, "free": 1}
            assert wear_reconcile(work, "E", "S") == after
        stale = {"batch": "E", "paper": "S", "steps": [step("C")], "released": True}
        with work.press_link.intercept(lambda dispatch, route, data: stale if route == "wear.state"
                                       else dispatch(route, data)):
            again = wear_reconcile(work, "E", "S")
        assert again == after
        work.reopen()
        assert work.press("pickup", piece_id=piece["piece_id"]) == piece
        assert work.issue("wear.balance", batch="E") == after
        return {"piece": piece, "pre": pre, "after": after, "reconcile_again": again}


def observe_guard(root):
    """Open-batch refusals and the ordinary-paper rules around a reserved plate."""
    with workshop(root) as work:
        seed_plates(work)
        seed_editions(work)
        arrive(work, "O", "one")  # ordinary order O uses edition `one` = [B]
        expect_problem("plate_in_use", lambda: wear_open(work, "X", "B", 1))
        expect_problem("unknown_plate", lambda: wear_open(work, "X", "Z", 1))
        assert wear_open(work, "G", "D", 1) == {"batch": "G", "plate": "D", "total": 1}
        assert wear_open(work, "G", "D", 1) == {"batch": "G", "plate": "D", "total": 1}
        expect_problem("batch_conflict", lambda: wear_open(work, "G", "D", 2))
        expect_problem("paper_conflict", lambda: wear_sign(work, "G", "O", "one", "sign-O"))
        assert wear_sign(work, "G", "M", "one", "sign-M") == {
            "batch": "G", "paper": "M", "original": "one", "request_id": "sign-M"}
        assert wear_sign(work, "G", "M", "one", "sign-M") == {
            "batch": "G", "paper": "M", "original": "one", "request_id": "sign-M"}
        expect_problem("request_conflict", lambda: wear_sign(work, "G", "M2", "one", "sign-M"))

        work.issue("layout", layout="dee", placements=steps("ABCD"), sequences=[steps("D")])
        work.issue("freeze", layout="dee", edition="dee")
        expect_problem("reserved_plate", lambda: work.issue("issue", paper="N", edition="dee"))
        expect_problem("reserved_plate", lambda: work.issue(
            "amend", paper="O", original="one", candidate="dee", request_id="change"))
        expect_problem("batch_paper_fixed", lambda: work.issue(
            "amend", paper="M", original="one", candidate="fork", request_id="mr"))
    return {"balance": {"batch": "G", "plate": "D", "total": 1, "used": 0, "held": 0, "free": 1}}


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python3 -B wear_fixture.py")
    with TemporaryDirectory(prefix="wear-v1-") as root:
        print(encode(observe_v1(root)))
