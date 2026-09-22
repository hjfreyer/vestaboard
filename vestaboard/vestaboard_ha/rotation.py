"""Picking at random without going round in circles.

A pick made uniformly at random repeats itself more than it looks like it
should: with six pieces in a category, one half-hour in six shows what is
already up, and a piece can sit out a whole afternoon while another comes round
three times. What is wanted is nearer a shuffle -- everything in its turn --
without the fixed order a shuffle would give.

So a rotation holds the last few picks back: with ``N`` things to choose from,
the last ``N // 2`` of them are out of the running and the pick is made from
the rest. That makes two things true however the randomness falls -- nothing
comes back until half of the others have been, and nothing is ever the thing
already up -- while which of the rest comes next stays unpredictable.

The memory is in the process and nowhere else. A restart starts the cycle over,
which is the right price for not writing a file every time the board changes.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

#: How many picks a rotation keeps per key. Only the last ``N // 2`` are ever
#: held back, so this is no more than a ceiling on a list that would otherwise
#: grow for as long as the app runs: past it the oldest picks go, since nothing
#: is ever going to consult them again.
REMEMBERED = 64


class Rotation:
    """Random picks that keep away from the ones lately made.

    One of these is as many rotations as it is given keys: the art library
    keeps one per category, so a piece shown at bedtime does not use up a
    daytime piece's turn. Anything with a single rotation leaves the key alone.
    """

    def __init__(self) -> None:
        self._recent: dict[str, list] = {}

    def choose(self, options: Sequence[T], key: str = "") -> T:
        """One of ``options`` at random, avoiding the ones lately chosen."""
        if not options:
            raise ValueError("there is nothing to choose from")

        held_back = self.held_back(len(options), key)
        fresh = [option for option in options if option not in held_back]
        # Half of them can never be all of them, so ``fresh`` has something in
        # it; the fallback is there so that a caller with something to show can
        # never be told there is nothing.
        chosen = random.choice(fresh or list(options))
        self.remember(chosen, key)
        return chosen

    def held_back(self, count: int, key: str = "") -> list:
        """The picks out of the running when choosing among ``count`` things.

        The last half of them, which is what makes a pair alternate, holds two
        of five back, and leaves a lone option always showable.
        """
        window = count // 2
        if not window:
            return []
        return self._recent.get(key, [])[-window:]

    def remember(self, chosen: T, key: str = "") -> None:
        """Note that something was shown, so the next picks keep away from it.

        Callers whose pick was made for them -- an automation naming the piece
        it wants -- say so here: as far as the board is concerned that is the
        thing that was just up, whoever chose it.
        """
        recent = self._recent.setdefault(key, [])
        recent.append(chosen)
        del recent[:-REMEMBERED]
