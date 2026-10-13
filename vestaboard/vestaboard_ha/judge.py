"""Claude's say on which holidays are worth a board.

Checkiday's several thousand holidays are not all of them worth cheering. Some
are a company's idea of a sales day, some are a trade's day that nobody in the
house has heard of, and some are solemn -- a memorial, a disease, a day of
mourning -- which is worse than dull on a board that puts ``HAPPY`` in front of
the name. So each holiday is put to Claude once, and Claude says which of the
three it is:

* ``show``: fun, silly or warmly celebratory, and fine behind a cheer.
* ``hide``: a brand's promotion, an industry's day, or just dull.
* ``sensitive``: solemn, tragic or divisive, where a cheer would be tone-deaf.

What Claude says is kept beside the holiday's name in ``holidays.py``, so a
holiday is asked about once however many years it comes round. The household
gets the last word, and two of its fields matter here: ``override``, which wins
over whatever Claude said, and ``exemplar``, which turns a holiday into one of
the examples every later question is asked with. The examples are what teach
Claude this house's taste rather than its own.

Every holiday in a question is numbered rather than named by its id, since a
short number is a good deal harder to copy back wrongly than 32 hex digits,
and an answer that leaves one out simply leaves it to be asked about again.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any, NamedTuple

import anthropic

from .checkiday import Holiday

_LOGGER = logging.getLogger(__name__)

#: What Claude may call a holiday. The first is the only one that goes up.
SHOW, HIDE, SENSITIVE = "show", "hide", "sensitive"
VERDICTS = (SHOW, HIDE, SENSITIVE)

#: Which Claude, and how hard it thinks. Sorting a few holidays a day is not
#: hard, so low effort is plenty, and it keeps an answer to seconds.
MODEL = "claude-opus-5-5"
EFFORT = "low"

#: Room for the answer, thinking included. A batch of holidays is a line each
#: and low effort thinks little, so this is far more than an answer needs; it
#: is only a ceiling on one that runs away.
MAX_TOKENS = 16000

#: How many holidays go in one question. A day is a dozen or so, so this only
#: matters when going back over the whole store at once.
BATCH = 50

#: How long one question may take, and how many more times the SDK asks after
#: a timeout, an overload or a dropped connection. Nothing is waiting on the
#: answer but the board, and a holiday nobody has judged simply waits its turn.
TIMEOUT = 120.0
RETRIES = 2

#: Server-side fallback: if a safety classifier declines the question -- not
#: likely about holiday names, but a list of memorials and diseases is the kind
#: of thing that could trip one -- the API answers it with another model rather
#: than with nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: What the answer has to look like. The API holds Claude to it, so what comes
#: back always parses; what it says still wants checking against what was asked.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "reason": {"type": "string"},
                },
                "required": ["n", "verdict", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

#: The standing instructions. The household's examples go after these.
INSTRUCTIONS = """\
You sort holidays for a split-flap board in a family kitchen. The board shows
one holiday at a time, with a cheerful phrase in front of it -- "HAPPY",
"IT'S", "WOWEE!", "OH BOY IT'S" -- so whatever goes up is being celebrated.

Put each holiday in exactly one of three categories:

- show: fun, silly, or warmly celebratory. It reads well with a cheer in front
  of it: food days, animal days, playful observances, seasons, warm traditions.
- sensitive: memorials, tragedies, diseases and other awareness causes, days of
  mourning, anything solemn or divisive. A cheer in front would be tone-deaf,
  however worthy the cause.
- hide: brand promotions ("National [Product] Day" invented by a company to sell
  something), trade or industry days nobody in the house would recognise, or
  names that are simply dull.

When a holiday could go either way between show and hide, ask whether it would
make someone in the kitchen smile. When it could be sensitive, it is.

For each holiday give its number, its category, and a short reason: one plain
sentence a person can read in a log."""


class JudgeError(RuntimeError):
    """Claude could not be asked, or its answer could not be used."""


class Verdict(NamedTuple):
    """What Claude said about one holiday."""

    id: str
    verdict: str
    reason: str = ""


class Exemplar(NamedTuple):
    """One of the household's examples: a name, and the verdict it should get."""

    name: str
    verdict: str
    reason: str = ""


def instructions(exemplars: Sequence[Exemplar] = ()) -> str:
    """The system prompt: the categories, then the household's own examples.

    The examples go in the order they are given, which the store keeps sorted,
    so the prompt only changes when an example does.
    """
    if not exemplars:
        return INSTRUCTIONS

    lines = [
        INSTRUCTIONS,
        "",
        "Here is how this household has sorted some holidays already. Follow "
        "their taste where it differs from your own:",
        "",
    ]
    for exemplar in exemplars:
        line = f"- {json.dumps(exemplar.name, ensure_ascii=False)} -> {exemplar.verdict}"
        if exemplar.reason:
            line += f": {exemplar.reason}"
        lines.append(line)
    return "\n".join(lines)


def question(holidays: Sequence[Holiday]) -> str:
    """The holidays to sort, each numbered from 1."""
    return "\n".join(
        [f"Sort these {len(holidays)} holidays:", ""]
        + [f"{n}. {holiday.name}" for n, holiday in enumerate(holidays, start=1)]
    )


def verdicts_in(text: str, holidays: Sequence[Holiday]) -> list[Verdict]:
    """What an answer says about the holidays it was asked about.

    A number that was not asked about, a second verdict for the same one, or a
    verdict that is not one of the three are each dropped with a word in the
    log; a holiday the answer leaves out is simply not judged, which means it
    is asked about again next time rather than guessed at now.
    """
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise JudgeError(f"{text[:200]!r} is not JSON") from exc

    entries = payload.get("verdicts") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise JudgeError(f"{text[:200]!r} has no list of verdicts in it")

    found: dict[int, Verdict] = {}
    for entry in entries:
        n = entry.get("n") if isinstance(entry, dict) else None
        verdict = entry.get("verdict") if isinstance(entry, dict) else None
        if not isinstance(n, int) or not 1 <= n <= len(holidays):
            _LOGGER.warning("judge: %r is not one of the holidays asked about", entry)
            continue
        if verdict not in VERDICTS:
            _LOGGER.warning("judge: %r is not a verdict; leaving it out", entry)
            continue
        if n in found:
            _LOGGER.warning("judge: %d was judged twice; keeping the first", n)
            continue
        found[n] = Verdict(
            holidays[n - 1].id, verdict, str(entry.get("reason") or "").strip()
        )

    missing = [
        holiday.name for n, holiday in enumerate(holidays, start=1) if n not in found
    ]
    if missing:
        _LOGGER.warning("judge: no verdict came back for %s", ", ".join(missing))

    return [found[n] for n in sorted(found)]


class Judge:
    """Asks Claude about holidays. One request per batch of them."""

    def __init__(self, api_key: str, *, client: Any = None) -> None:
        """``client`` is for the tests; anything else gets the real one."""
        if client is None and api_key:
            client = anthropic.AsyncAnthropic(
                api_key=api_key, timeout=TIMEOUT, max_retries=RETRIES
            )
        self._client = client

    @property
    def configured(self) -> bool:
        """Whether there is a key to ask with. Without one, nothing is judged."""
        return self._client is not None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def verdicts(
        self, holidays: Sequence[Holiday], exemplars: Sequence[Exemplar] = ()
    ) -> list[Verdict]:
        """Claude's verdict on each of ``holidays``, as far as it gave one."""
        if self._client is None:
            raise JudgeError("no Anthropic API key configured")
        if not holidays:
            return []

        try:
            response = await self._client.beta.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=instructions(exemplars),
                messages=[{"role": "user", "content": question(holidays)}],
                output_config={
                    "effort": EFFORT,
                    "format": {"type": "json_schema", "schema": SCHEMA},
                },
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIError as exc:
            raise JudgeError(f"asking Claude went wrong: {exc}") from exc

        # A refusal or a ceiling hit leaves an answer that is not all there,
        # and a holiday judged on half an answer is worse than one not judged.
        if response.stop_reason == "refusal":
            raise JudgeError(f"Claude declined to sort {len(holidays)} holidays")
        if response.stop_reason == "max_tokens":
            raise JudgeError(f"Claude ran out of room sorting {len(holidays)} holidays")

        text = next(
            (block.text for block in response.content if block.type == "text"), ""
        )
        return verdicts_in(text, holidays)
