from dataclasses import asdict

from bench import intake, occupancy, returns, unmount
from bench.mount import mount_sheet
from handoff import history, release
from handoff.completion import check_completion
from issue.tickets import decode_ticket
from press import adoption, receipts, sheets
from press.impressions import submit_impression
from proof.freeze import decode_edition
from runtime import (Problem, install_sample, install_schema, invoke, local_url, positive,
                     serve, service_arguments, text, transaction)


def _accept_arrival(db, paper, label, order):
    frozen = decode_edition(order['edition'])
    sheets.remember_edition(db, frozen)
    return intake.register_arrival(db, paper, label, order)


def initialize_press(path, sample_order=None):
    with transaction(path, write=True) as db:
        editions, physical, impressions = sheets.SCHEMA
        install_schema(db, (editions, intake.SCHEMA, *occupancy.SCHEMA, unmount.SCHEMA,
                            returns.SCHEMA, physical, impressions, receipts.SCHEMA,
                            adoption.SCHEMA, release.SCHEMA, history.SCHEMA))
        if sample_order is not None:
            def load(connection):
                from day import SAMPLE_PAPER
                _accept_arrival(connection, SAMPLE_PAPER, SAMPLE_PAPER, sample_order(SAMPLE_PAPER))

            install_sample(db, 'workshop-day-v1', load)


class PressService:
    def __init__(self, path, issue_url, *, sample=False):
        self.path = path
        self.issue_url = issue_url
        initialize_press(path, self._order if sample else None)

    def _order(self, paper):
        return invoke(self.issue_url, 'order', {'paper': paper})

    def dispatch(self, route, data):
        if route == 'press':
            return self._press(data)
        if route == 'adopt':
            return self._adopt(data)
        if route == 'stage' and data.get('action') == 'arrive':
            paper = text(data.get('paper'), 'paper')
            label = text(data.get('label'), 'label')
            order = self._order(paper)
            with transaction(self.path, write=True) as db:
                return asdict(_accept_arrival(db, paper, label, order))
        with transaction(self.path, write=route in ('stage', 'release', 'pickup')) as db:
            return self._local(db, route, data)

    def _press(self, data):
        paper = text(data.get('paper'), 'paper')
        ticket_id = positive(data.get('ticket_id'), 'ticket_id')
        with transaction(self.path) as db:
            previous = receipts.find_receipt(db, paper, ticket_id)
            if previous is not None:
                return asdict(previous)
        ticket = decode_ticket(invoke(self.issue_url, 'ticket.read', {'ticket_id': ticket_id}))
        with transaction(self.path, write=True) as db:
            return asdict(submit_impression(db, paper, ticket))

    def _adopt(self, data):
        paper = text(data.get('paper'), 'paper')
        request_id = text(data.get('request_id'), 'request_id')
        with transaction(self.path) as db:
            old = adoption.read_adoption_decision(db, paper, request_id)
            if old is not None:
                return asdict(old)
        request = invoke(self.issue_url, 'amend.record', {'paper': paper, 'request_id': request_id})
        candidate = decode_edition(request['candidate_edition'])
        with transaction(self.path, write=True) as db:
            return asdict(adoption.decide_adoption(db, request, candidate))

    def _local(self, db, route, data):
        if route in ('pickup', 'pickup.history'):
            piece_id = text(data.get('piece_id'), 'piece_id')
            if route == 'pickup':
                return asdict(history.pickup_piece(db, piece_id))
            return [asdict(pickup) for pickup in history.list_pickups(db, piece_id)]
        if route not in ('impressions', 'receipt', 'adopt.status', 'stage', 'stage.status', 'release'):
            raise Problem('unknown_operation', f'Unknown press operation {route}', 404)
        paper = text(data.get('paper'), 'paper')
        if route == 'impressions':
            intake.read_arrival(db, paper)
            return [asdict(item) for item in sheets.list_impressions(db, paper)]
        if route == 'receipt':
            receipt = receipts.find_receipt(db, paper, positive(data.get('ticket_id'), 'ticket_id'))
            if receipt is None:
                raise Problem('unknown_receipt', 'No original receipt for this paper and ticket', 404)
            return asdict(receipt)
        if route == 'adopt.status':
            decision = adoption.read_adoption_decision(db, paper, text(data.get('request_id'), 'request_id'))
            return None if decision is None else asdict(decision)
        if route == 'stage':
            return self._stage(db, paper, data)
        if route == 'stage.status':
            arrival = intake.read_arrival(db, paper)
            returned = returns.read_return(db, paper)
            removed = unmount.read_unmount(db, paper)
            return {'arrival': asdict(arrival), 'mounts': [asdict(mount) for mount in occupancy.list_mounts(db, paper)],
                    'return': None if returned is None else asdict(returned),
                    'unmount': None if removed is None else asdict(removed)}
        return asdict(release.release_piece(db, paper))

    def _stage(self, db, paper, data):
        action = data.get('action')
        if action == 'return':
            return asdict(returns.return_arrival(db, paper))
        if action not in ('mount', 'unmount'):
            raise Problem('invalid_stage_action', 'Expected arrive, mount, return, or unmount', 400)
        mount_id = text(data.get('mount_id'), 'mount_id')
        if action == 'mount':
            mount = mount_sheet(db, paper, mount_id)
            original = intake.read_arrival(db, paper).original
            sheets.open_sheet(db, mount, original)
            return asdict(mount)
        check_completion(db, paper)
        return asdict(unmount.unmount_sheet(db, paper, mount_id))


def main():
    args = service_arguments('Workshop press service', 8702, 8701)
    service = PressService(args.db, local_url(args.peer_port), sample=args.sample)
    serve(service.dispatch, args.port)


if __name__ == '__main__':
    main()
