import random
from collections import Counter

import pytest

from pdf_assistant.ai import Provider
from pdf_assistant.ai.factory import ModelRef
from pdf_assistant.chat.components import Experiment, Tally


def _experiment(enabled: bool = True) -> Experiment:
    return Experiment(
        models=[ModelRef(Provider.ANTHROPIC, "claude-opus-5-5"), ModelRef(Provider.OPENAI, "gpt-5.1")],
        top_ks=[1, 3, 5, 21],
        memory_turns=[0, 1, 2, 5],
        enabled=enabled,
    )


def test_labels_are_serbian_with_the_right_plural() -> None:
    experiment = _experiment()
    assert [c.label for c in experiment.components("retriever")] == ["1 isečak", "3 isečka", "5 isečaka", "21 isečak"]
    assert [c.label for c in experiment.components("memory")] == [
        "cela istorija",
        "poslednje pitanje",
        "poslednja 2 pitanja",
        "poslednjih 5 pitanja",
    ]
    assert [c.label for c in experiment.components("llm")] == ["claude-opus-5-5", "gpt-5.1"]
    assert experiment.components("llm")[1].name == "openai:gpt-5.1"


def test_satisfaction_and_weight() -> None:
    assert Tally().satisfaction is None and Tally().weight == 1.0
    assert Tally(up=3, down=1).satisfaction == 0.75
    assert Tally(down=1).weight == 0.5
    assert Tally(down=50).weight == 0.1  # the floor


def test_weights_follow_the_votes_and_sum_to_one() -> None:
    weights = _experiment().weights("llm", {"anthropic:claude-opus-5-5": Tally(up=1), "openai:gpt-5.1": Tally(down=1)})
    assert weights == pytest.approx({"anthropic:claude-opus-5-5": 2 / 3, "openai:gpt-5.1": 1 / 3})
    assert _experiment(enabled=False).weights("llm", {}) == {"anthropic:claude-opus-5-5": 1.0, "openai:gpt-5.1": 0.0}


def test_pick_draws_by_weight() -> None:
    experiment = _experiment()
    rng = random.Random(7)
    tallies = {"anthropic:claude-opus-5-5": Tally(up=9), "openai:gpt-5.1": Tally(down=9)}
    picks = Counter(experiment.pick("llm", tallies, rng).name for _ in range(2000))
    # weights 1.0 and 0.1: about 91% and 9%
    assert 0.86 < picks["anthropic:claude-opus-5-5"] / 2000 < 0.95
    assert picks["openai:gpt-5.1"] > 0


def test_components_that_are_no_longer_configured() -> None:
    experiment = _experiment()
    gone = experiment.describe("llm", "ollama:llama3.2")
    assert not gone.active and gone.label == "llama3.2"
    assert experiment.resolve("llm", "ollama:llama3.2").name == "anthropic:claude-opus-5-5"
    assert experiment.top_k("top_99") == 1 and experiment.top_k("top_5") == 5
    assert experiment.memory_turns("last_9_turns") == 0 and experiment.memory_turns("last_2_turns") == 2
