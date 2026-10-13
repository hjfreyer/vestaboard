import json

import anthropic
import httpx2
import pytest

from vestaboard_ha import judge
from vestaboard_ha.checkiday import Holiday
from vestaboard_ha.judge import Exemplar, Judge, JudgeError, Verdict

SPINACH = Holiday("676cd91e31adcacd0a505117d2c4a842", "Fresh Spinach Day")
PAYROLL = Holiday("adcacd0a505117d2c4a842676cd91e31", "National Payroll Week")
MEMORIAL = Holiday("31adcacd0a505117d2c4a842676cd91e", "Pearl Harbor Remembrance Day")


def answer(*verdicts):
    """An answer in the shape the schema holds Claude to."""
    return json.dumps(
        {"verdicts": [{"n": n, "verdict": v, "reason": r} for n, v, r in verdicts]}
    )


def test_with_no_exemplars_the_prompt_is_the_instructions_alone():
    assert judge.instructions() == judge.INSTRUCTIONS


def test_the_exemplars_follow_the_instructions_one_a_line():
    prompt = judge.instructions(
        [
            Exemplar("Fresh Spinach Day", "show", "A silly food day"),
            Exemplar("National Payroll Week", "hide"),
        ]
    )

    assert prompt.startswith(judge.INSTRUCTIONS)
    assert '- "Fresh Spinach Day" -> show: A silly food day' in prompt
    # An exemplar with no reason is the verdict and nothing after it.
    assert prompt.endswith('- "National Payroll Week" -> hide')


def test_the_question_numbers_the_holidays_from_one():
    asked = judge.question([SPINACH, PAYROLL])

    assert "1. Fresh Spinach Day" in asked
    assert "2. National Payroll Week" in asked
    # The ids are ours to keep track of; Claude only ever sees the numbers.
    assert SPINACH.id not in asked


def test_an_answer_s_numbers_come_back_as_the_holidays_they_stood_for():
    verdicts = judge.verdicts_in(
        answer((2, "hide", "Nobody here runs payroll"), (1, "show", "Fun")),
        [SPINACH, PAYROLL],
    )

    assert verdicts == [
        Verdict(SPINACH.id, "show", "Fun"),
        Verdict(PAYROLL.id, "hide", "Nobody here runs payroll"),
    ]


def test_what_was_not_asked_about_is_left_out(caplog):
    verdicts = judge.verdicts_in(
        answer((1, "show", "Fun"), (7, "show", "Who?"), (0, "hide", "Nobody")),
        [SPINACH],
    )

    assert verdicts == [Verdict(SPINACH.id, "show", "Fun")]
    assert "not one of the holidays asked about" in caplog.text


def test_a_holiday_judged_twice_keeps_its_first_verdict(caplog):
    verdicts = judge.verdicts_in(
        answer((1, "show", "Fun"), (1, "hide", "Dull")), [SPINACH]
    )

    assert verdicts == [Verdict(SPINACH.id, "show", "Fun")]
    assert "judged twice" in caplog.text


def test_a_holiday_left_out_of_the_answer_is_left_unjudged(caplog):
    verdicts = judge.verdicts_in(answer((1, "show", "Fun")), [SPINACH, MEMORIAL])

    assert verdicts == [Verdict(SPINACH.id, "show", "Fun")]
    assert "no verdict came back for Pearl Harbor Remembrance Day" in caplog.text


def test_a_verdict_that_is_not_one_of_the_three_is_left_out(caplog):
    verdicts = judge.verdicts_in(answer((1, "maybe", "Hmm")), [SPINACH])

    assert verdicts == []
    assert "is not a verdict" in caplog.text


def test_an_answer_that_is_not_one_is_an_error():
    with pytest.raises(JudgeError, match="not JSON"):
        judge.verdicts_in("I think they are all lovely", [SPINACH])
    with pytest.raises(JudgeError, match="no list of verdicts"):
        judge.verdicts_in("{}", [SPINACH])


@pytest.mark.asyncio
async def test_no_key_is_a_judge_that_will_not_ask():
    unconfigured = Judge("")

    assert not unconfigured.configured
    with pytest.raises(JudgeError, match="no Anthropic API key"):
        await unconfigured.verdicts([SPINACH])
    # Closing one that never opened anything is nothing to worry about.
    await unconfigured.close()


class FakeAPI:
    """The Messages API, as far as a real client can tell: the requests it got,
    and whatever response it is told to give back."""

    def __init__(self, status=200, *, text="", stop_reason="end_turn"):
        self.status = status
        self.text = text
        self.stop_reason = stop_reason
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        if self.status != 200:
            return httpx2.Response(
                self.status,
                json={"type": "error", "error": {"type": "api_error", "message": "no"}},
            )
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": judge.MODEL,
                "content": [{"type": "text", "text": self.text}],
                "stop_reason": self.stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    def judge(self):
        """A Judge whose client is the real SDK, talking to this."""
        client = anthropic.AsyncAnthropic(
            api_key="test-key",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self)),
        )
        return Judge("test-key", client=client)


@pytest.mark.asyncio
async def test_a_question_goes_out_the_way_the_api_wants_it():
    api = FakeAPI(text=answer((1, "show", "Fun")))

    verdicts = await api.judge().verdicts(
        [SPINACH], [Exemplar("National Payroll Week", "hide", "Dull")]
    )

    assert verdicts == [Verdict(SPINACH.id, "show", "Fun")]
    [request] = api.requests
    body = json.loads(request.content)
    assert body["model"] == judge.MODEL
    assert body["output_config"] == {
        "effort": judge.EFFORT,
        "format": {"type": "json_schema", "schema": judge.SCHEMA},
    }
    assert body["fallbacks"] == "default"
    assert judge.FALLBACK_BETA in request.headers["anthropic-beta"]
    assert '"National Payroll Week" -> hide: Dull' in body["system"]
    assert "1. Fresh Spinach Day" in body["messages"][0]["content"]


@pytest.mark.asyncio
async def test_an_api_that_says_no_is_a_judge_error():
    api = FakeAPI(500)

    with pytest.raises(JudgeError, match="asking Claude went wrong"):
        await api.judge().verdicts([SPINACH])


@pytest.mark.asyncio
async def test_a_refusal_judges_nothing():
    api = FakeAPI(text="", stop_reason="refusal")

    with pytest.raises(JudgeError, match="declined"):
        await api.judge().verdicts([SPINACH])


@pytest.mark.asyncio
async def test_an_answer_cut_off_judges_nothing():
    api = FakeAPI(text='{"verdicts": [{"n": 1', stop_reason="max_tokens")

    with pytest.raises(JudgeError, match="ran out of room"):
        await api.judge().verdicts([SPINACH])


@pytest.mark.asyncio
async def test_nothing_to_ask_about_is_not_asked():
    api = FakeAPI()

    assert await api.judge().verdicts([]) == []
    assert api.requests == []
