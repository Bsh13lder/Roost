"""How long one screen input may take (security review b): typing gets time for its length.

``roost-input`` keeps the whole input to ``input_budget_s`` (docker/computer/roost_input.py mirrors it, a test keeps
the two equal), the keeper waits ``CU_INPUT_TIMEOUT_GRACE_S`` longer, and the desk longer still, so the process inside
the computer always stops itself before anything outside gives up on it."""

from __future__ import annotations

from roost.constants import CU_INPUT_TIMEOUT_GRACE_S, CU_INPUT_TIMEOUT_S, CU_TYPE_DELAY_MS, CU_TYPE_TIMEOUT_FACTOR

_MS_PER_S = 1000


def input_budget_s(text_chars: int = 0) -> float:
    """roost-input's own deadline for one input that types ``text_chars`` characters (0 for any other verb)."""
    return CU_INPUT_TIMEOUT_S + text_chars * CU_TYPE_DELAY_MS / _MS_PER_S * CU_TYPE_TIMEOUT_FACTOR


def keeper_input_timeout_s(text_chars: int = 0) -> float:
    """How long the keeper waits for ``docker exec ... roost-input`` before killing it."""
    return input_budget_s(text_chars) + CU_INPUT_TIMEOUT_GRACE_S


def desk_input_timeout_s(text_chars: int = 0) -> float:
    """How long the desk waits for the keeper's answer."""
    return keeper_input_timeout_s(text_chars) + CU_INPUT_TIMEOUT_GRACE_S
