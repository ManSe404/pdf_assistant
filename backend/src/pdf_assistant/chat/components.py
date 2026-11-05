"""The experiment: which language model, how many retrieved passages and how much
conversation history work best, judged by the users' thumbs up and down.

Each new conversation draws one component of each kind at random, weighted by how
satisfied users were with it: ``(up + 1) / (up + down + 1)``, at least 0.1. The "+1" is
one imaginary thumbs up, so a component nobody voted on yet counts as fully satisfying
and gets tried; the floor keeps a badly rated component from disappearing completely.
"""

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pdf_assistant.ai.factory import ModelRef

Kind = Literal["llm", "retriever", "memory"]
KINDS: tuple[Kind, ...] = ("llm", "retriever", "memory")
MIN_WEIGHT = 0.1


@dataclass(frozen=True)
class Component:
    kind: Kind
    name: str
    label: str
    active: bool = True


@dataclass(frozen=True)
class Tally:
    up: int = 0
    down: int = 0

    @property
    def satisfaction(self) -> float | None:
        total = self.up + self.down
        return self.up / total if total else None

    @property
    def weight(self) -> float:
        return max((self.up + 1) / (self.up + self.down + 1), MIN_WEIGHT)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Serbian: 1 isečak, 2 isečka, 5 isečaka; 21 isečak, 12 isečaka."""
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def retriever_name(top_k: int) -> str:
    return f"top_{top_k}"


def memory_name(turns: int) -> str:
    return "all_history" if turns == 0 else f"last_{turns}_turns"


def _retriever_label(top_k: int) -> str:
    return f"{top_k} {_plural(top_k, 'isečak', 'isečka', 'isečaka')}"


def _memory_label(turns: int) -> str:
    if turns == 0:
        return "cela istorija"
    if turns == 1:
        return "poslednje pitanje"
    if turns <= 4:
        return f"poslednja {turns} pitanja"
    return f"poslednjih {turns} pitanja"


class Experiment:
    def __init__(
        self,
        *,
        models: Sequence[ModelRef],
        top_ks: Sequence[int],
        memory_turns: Sequence[int],
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self._top_k = {retriever_name(k): k for k in dict.fromkeys(top_ks)}
        self._turns = {memory_name(t): t for t in dict.fromkeys(memory_turns)}
        self._components: dict[Kind, list[Component]] = {
            "llm": [Component("llm", ref.key, ref.model) for ref in models],
            "retriever": [Component("retriever", name, _retriever_label(k)) for name, k in self._top_k.items()],
            "memory": [Component("memory", name, _memory_label(t)) for name, t in self._turns.items()],
        }

    def components(self, kind: Kind) -> list[Component]:
        """The configured components of one kind, in configuration order."""
        return list(self._components[kind])

    def default(self, kind: Kind) -> Component:
        return self._components[kind][0]

    def describe(self, kind: Kind, name: str) -> Component:
        """The component by name; one that is no longer configured comes back inactive."""
        for component in self._components[kind]:
            if component.name == name:
                return component
        label = name.partition(":")[2] if kind == "llm" and ":" in name else name
        return Component(kind, name, label, active=False)

    def resolve(self, kind: Kind, name: str) -> Component:
        """The component to actually use: the named one, or the default when it is gone."""
        component = self.describe(kind, name)
        return component if component.active else self.default(kind)

    def top_k(self, name: str) -> int:
        return self._top_k[self.resolve("retriever", name).name]

    def memory_turns(self, name: str) -> int:
        return self._turns[self.resolve("memory", name).name]

    def weights(self, kind: Kind, tallies: Mapping[str, Tally]) -> dict[str, float]:
        """Selection probability of each configured component (sums to 1)."""
        components = self._components[kind]
        if not self.enabled:
            return {c.name: (1.0 if i == 0 else 0.0) for i, c in enumerate(components)}
        raw = {c.name: tallies.get(c.name, Tally()).weight for c in components}
        total = sum(raw.values())
        return {name: w / total for name, w in raw.items()}

    def pick(self, kind: Kind, tallies: Mapping[str, Tally], rng: random.Random | None = None) -> Component:
        weights = self.weights(kind, tallies)
        names = list(weights)
        chosen = (rng or random).choices(names, weights=[weights[n] for n in names], k=1)[0]
        return self.describe(kind, chosen)
