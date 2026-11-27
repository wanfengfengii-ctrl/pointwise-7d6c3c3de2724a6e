import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from day import arrive, finish, mount, steps, ticket
from issue.service import IssueService
from press.service import PressService
from runtime import Unavailable, encode, invoke, make_server, running


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


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python3 -B wear_fixture.py")
    with TemporaryDirectory(prefix="wear-v1-") as root:
        print(encode(observe_v1(root)))
