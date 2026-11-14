"""DSL rewrites applied before the engine runs a program.

``Forbidden`` is sugar so the parser never writes a double negative:

    Forbidden(a, v, when)              -> Verify(Permitted(a, v, when), expect=False)
    Forbidden(..., interval, all)      -> Verify(Permitted(..., interval, any), expect=False)
    Forbidden(..., interval, any)      -> Verify(Permitted(..., interval, all), expect=False)

"forbidden at every moment" is "not permitted at any moment", and "forbidden at
some moment" is "not permitted at every moment".
"""

from __future__ import annotations

from vqa.schemas import (
    ChoiceOption, Choose, Forbidden, Permitted, Program, Quantifier, Verify, When,
)

_FLIP = {Quantifier.all: Quantifier.any, Quantifier.any: Quantifier.all}


def _flip(when: When | None) -> When | None:
    if when is None or when.quantifier is None:
        return when
    return when.model_copy(update={"quantifier": _FLIP[when.quantifier]})


def _permitted(f: Forbidden) -> Permitted:
    return Permitted(action=f.action, vehicle=f.vehicle, when=_flip(f.when), sign=f.sign)


def normalize(p: Program) -> Program:
    """Rewrite Forbidden into Verify(Permitted, expect=False), recursively."""
    if isinstance(p, Forbidden):
        return Verify(claim=_permitted(p), expect=False)
    if isinstance(p, Verify) and isinstance(p.claim, Forbidden):
        return Verify(claim=_permitted(p.claim), expect=not p.expect)
    if isinstance(p, Choose):
        opts = []
        for o in p.options:
            if isinstance(o.claim, Forbidden):
                opts.append(ChoiceOption(label=o.label, claim=_permitted(o.claim),
                                         expect=not o.expect))
            else:
                opts.append(o)
        return Choose(options=opts)
    return p
