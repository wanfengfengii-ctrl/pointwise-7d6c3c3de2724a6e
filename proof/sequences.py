from dataclasses import dataclass

from proof.layouts import require_placement
from proof.steps import PrintStep
from runtime import Problem


@dataclass(frozen=True)
class SequenceMatch:
    compatible: tuple[tuple[PrintStep, ...], ...]
    next_steps: tuple[PrintStep, ...]
    complete: bool


def validate_sequences(db, layout):
    if not layout.sequences or any(not sequence for sequence in layout.sequences):
        raise Problem('empty_sequence', 'Every frozen alternative must contain an impression', 400)
    for sequence in layout.sequences:
        for step in sequence:
            require_placement(db, layout, step)
    return layout.sequences


def match_prefix(sequences, prefix):
    prefix = tuple(prefix)
    size = len(prefix)
    compatible = tuple(sequence for sequence in sequences if sequence[:size] == prefix)
    next_steps = tuple(dict.fromkeys(sequence[size] for sequence in compatible if len(sequence) > size))
    complete = any(len(sequence) == size for sequence in compatible)
    return SequenceMatch(compatible, next_steps, complete)


def contains_ticket_step(sequences, position, step):
    return any(len(sequence) >= position and sequence[position - 1] == step for sequence in sequences)
