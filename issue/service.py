from dataclasses import asdict

from issue import evidence, lookup, orders, tickets, wear
from issue.amendments import record_known_decision, submit_amendment
from proof import freeze, layouts, plates
from proof.steps import parse_step
from runtime import (Problem, Unavailable, install_sample, install_schema, invoke,
                     local_url, positive, serve, service_arguments, text, transaction)


def initialize_issue(path, sample=False):
    with transaction(path, write=True) as db:
        install_schema(db, (plates.SCHEMA, layouts.SCHEMA, freeze.SCHEMA, orders.SCHEMA,
                            *lookup.SCHEMA, tickets.SCHEMA, evidence.SCHEMA, *wear.SCHEMA))
        if sample:
            from day import day_layouts, SAMPLE_PAPER

            def load(connection):
                for layout in day_layouts():
                    for step in layout['placements']:
                        plate = step['plate']
                        plates.register_plate(connection, plate, f'印版 {plate}')
                    layouts.save_layout(connection, **layout)
                freeze.freeze_edition(connection, 'lesson', 'sample-edition')
                orders.issue_order(connection, SAMPLE_PAPER, 'sample-edition')

            install_sample(db, 'workshop-day-v1', load)


class IssueService:
    def __init__(self, path, press_url, *, sample=False):
        self.path = path
        self.press_url = press_url
        initialize_issue(path, sample)

    def dispatch(self, route, data):
        if route in ('amend', 'amend.status'):
            return self._amend(route, data)
        if route == 'receive':
            return self._receive(data)
        if route == 'wear.reconcile':
            return self._reconcile(data)
        write = route in ('plate', 'layout', 'freeze', 'issue', 'ticket', 'wear.open', 'wear.issue')
        with transaction(self.path, write=write) as db:
            return self._local(db, route, data)

    def _reconcile(self, data):
        batch = text(data.get('batch'), 'batch')
        paper = text(data.get('paper'), 'paper')
        with transaction(self.path) as db:
            wear.paper_payload(db, batch, paper)
        state = invoke(self.press_url, 'wear.state', {'batch': batch, 'paper': paper})
        with transaction(self.path, write=True) as db:
            wear.record_verified(db, batch, paper, state)
            return wear.compute_balance(db, batch)

    def _amend(self, route, data):
        if route == 'amend':
            with transaction(self.path, write=True) as db:
                record = submit_amendment(db, data)
            press_route = 'adopt'
        else:
            with transaction(self.path) as db:
                record = lookup.read_request_status(db, text(data.get('paper'), 'paper'),
                                                    text(data.get('request_id'), 'request_id'))
            press_route = 'adopt.status'
        if record.decision is not None:
            return asdict(record)
        try:
            decision = invoke(self.press_url, press_route,
                              {'paper': record.paper, 'request_id': record.request_id})
        except Unavailable:
            decision = None
        with transaction(self.path, write=decision is not None) as db:
            if decision is None:
                current = lookup.read_request_status(db, record.paper, record.request_id)
            else:
                current = record_known_decision(db, record, decision)
            return asdict(current)

    def _receive(self, data):
        paper = text(data.get('paper'), 'paper')
        ticket_id = positive(data.get('ticket_id'), 'ticket_id')
        with transaction(self.path) as db:
            ticket = tickets.read_ticket(db, ticket_id)
        if ticket.paper != paper:
            raise Problem('wrong_paper', 'The official ticket belongs to a different paper')
        receipt = invoke(self.press_url, 'receipt', {'paper': paper, 'ticket_id': ticket_id})
        with transaction(self.path, write=True) as db:
            return asdict(evidence.record_received_receipt(db, ticket, receipt))

    def _local(self, db, route, data):
        if route == 'plate':
            return asdict(plates.register_plate(db, data.get('plate'), data.get('name')))
        if route == 'layout':
            return asdict(layouts.save_layout(db, data.get('layout'), data.get('placements'),
                                             data.get('sequences')))
        if route == 'layout.read':
            return asdict(layouts.read_layout(db, text(data.get('layout'), 'layout')))
        if route == 'freeze':
            frozen = freeze.freeze_edition(db, text(data.get('layout'), 'layout'), data.get('edition'))
            return freeze.edition_payload(frozen)
        if route == 'edition':
            return freeze.edition_payload(freeze.read_frozen_edition(db, text(data.get('edition'), 'edition')))
        if route == 'wear.open':
            return wear.open_batch(db, data.get('batch'), data.get('plate'), data.get('total'))
        if route == 'wear.issue':
            return wear.issue_wear_paper(db, data)
        if route == 'wear.balance':
            return wear.compute_balance(db, text(data.get('batch'), 'batch'))
        if route == 'wear.paper':
            paper = text(data.get('paper'), 'paper')
            if 'batch' in data:
                return wear.paper_payload(db, text(data.get('batch'), 'batch'), paper)
            return wear.paper_by_paper(db, paper)
        if route == 'ticket.read':
            return asdict(tickets.read_ticket(db, positive(data.get('ticket_id'), 'ticket_id')))
        if route in ('issue', 'order', 'ticket', 'received', 'amend.record'):
            return self._paper_operation(db, route, text(data.get('paper'), 'paper'), data)
        raise Problem('unknown_operation', f'Unknown issue operation {route}', 404)

    def _paper_operation(self, db, route, paper, data):
        if route == 'issue':
            edition = text(data.get('edition'), 'edition')
            if not wear.is_batch_paper(db, paper):
                wear.reject_reserved_edition(db, edition)
            return asdict(orders.issue_order(db, paper, edition))
        if route == 'order':
            order = orders.read_order(db, paper)
            return {**asdict(order), 'edition': freeze.edition_payload(freeze.read_frozen_edition(db, order.original))}
        if route == 'ticket':
            return asdict(tickets.issue_ticket(db, paper, data.get('position'), parse_step(data.get('step'))))
        if route == 'received':
            return [asdict(receipt) for receipt in evidence.list_received_receipts(db, paper)]
        record = lookup.read_request_status(db, paper, text(data.get('request_id'), 'request_id'))
        candidate = freeze.edition_payload(freeze.read_frozen_edition(db, record.candidate))
        return {**asdict(record), 'candidate_edition': candidate}


def main():
    args = service_arguments('Workshop issue service', 8701, 8702)
    service = IssueService(args.db, local_url(args.peer_port), sample=args.sample)
    serve(service.dispatch, args.port)


if __name__ == '__main__':
    main()
