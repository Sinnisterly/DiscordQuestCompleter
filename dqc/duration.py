"""Parsing for the duration field.

Accepts plain seconds, colon/unit notation and small arithmetic expressions:

    900            -> 900
    15m            -> 900
    1h30m          -> 5400
    25:00          -> 1500
    10 * 60        -> 600
    (3 * 60) + 20  -> 200

Arithmetic goes through the ``ast`` module with an operator allowlist rather
than ``eval``, so a pasted expression can never execute arbitrary code.
"""

import ast
import operator
import re

DEFAULT_SECONDS = 900
MAX_SECONDS = 24 * 60 * 60

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_UNIT_RE = re.compile(
    r'^\s*(?:(?P<h>\d+(?:\.\d+)?)\s*h)?'
    r'\s*(?:(?P<m>\d+(?:\.\d+)?)\s*m)?'
    r'\s*(?:(?P<s>\d+(?:\.\d+)?)\s*s)?\s*$',
    re.IGNORECASE,
)


class DurationError(ValueError):
    """Raised when the text cannot be read as a duration."""


def _eval_node(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise DurationError('only numbers are allowed')
        return node.value
    if isinstance(node, ast.BinOp):
        fn = _BIN_OPS.get(type(node.op))
        if fn is None:
            raise DurationError('unsupported operator')
        return fn(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        fn = _UNARY_OPS.get(type(node.op))
        if fn is None:
            raise DurationError('unsupported operator')
        return fn(_eval_node(node.operand))
    raise DurationError('unsupported expression')


def _from_clock(text: str):
    """``25:00`` -> 1500, ``1:05:00`` -> 3900. Returns None if not clock form."""
    parts = text.split(':')
    if len(parts) not in (2, 3) or not all(p.strip().isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return nums[0] * 3600 + nums[1] * 60 + nums[2]


def parse_duration(text, default: int = DEFAULT_SECONDS) -> int:
    """Return a whole number of seconds. Blank input yields ``default``."""
    if text is None:
        return default
    text = str(text).strip()
    if not text:
        return default

    seconds = None

    clock = _from_clock(text)
    if clock is not None:
        seconds = clock

    if seconds is None:
        unit = _UNIT_RE.match(text)
        if unit and any(unit.group(g) for g in ('h', 'm', 's')):
            seconds = (
                float(unit.group('h') or 0) * 3600
                + float(unit.group('m') or 0) * 60
                + float(unit.group('s') or 0)
            )

    if seconds is None:
        try:
            tree = ast.parse(text, mode='eval')
        except SyntaxError as exc:
            raise DurationError(f'{text!r} is not a valid duration') from exc
        seconds = _eval_node(tree.body)

    if seconds != seconds or seconds in (float('inf'), float('-inf')):
        raise DurationError('duration is not a finite number')

    seconds = int(round(seconds))
    if seconds <= 0:
        raise DurationError('duration must be greater than zero')
    if seconds > MAX_SECONDS:
        raise DurationError('duration may not exceed 24 hours')
    return seconds


def format_duration(seconds) -> str:
    """``5400`` -> ``1h 30m``. Used for labels and the countdown."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if hours:
        parts.append(f'{hours}h')
    if minutes:
        parts.append(f'{minutes}m')
    if secs or not parts:
        parts.append(f'{secs}s')
    return ' '.join(parts)
