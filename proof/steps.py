from dataclasses import dataclass

from runtime import Problem, array, text


@dataclass(frozen=True)
class PrintStep:
    plate: str
    placement: str


def parse_step(value):
    if not isinstance(value, dict):
        raise Problem('invalid_step', 'A print step must be an object', 400)
    return PrintStep(text(value.get('plate'), 'plate'), text(value.get('placement'), 'placement'))


def step_payload(step):
    return {'plate': step.plate, 'placement': step.placement}


def parse_sequences(value):
    return tuple(tuple(parse_step(step) for step in array(sequence, 'sequence'))
                 for sequence in array(value, 'sequences'))


def sequence_payload(sequences):
    return [[step_payload(step) for step in sequence] for sequence in sequences]
