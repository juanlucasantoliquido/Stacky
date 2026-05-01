from dataclasses import asdict, dataclass


@dataclass
class PackStep:
    agent_type: str
    chain_from_previous: bool = True
    pause_after: bool = True
    skip_if_approved_within: str | None = None  # ej: "24h"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PackDefinition:
    id: str
    name: str
    description: str
    steps: list[PackStep]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
        }


PACKS: dict[str, PackDefinition] = {
    "desarrollo": PackDefinition(
        id="desarrollo",
        name="Pack Desarrollo",
        description="Functional → Technical → Developer → QA, con pausa entre pasos.",
        steps=[
            PackStep("functional", chain_from_previous=False),
            PackStep("technical"),
            PackStep("developer"),
            PackStep("qa"),
        ],
    ),
    "qa-express": PackDefinition(
        id="qa-express",
        name="Pack QA Express",
        description="Validación rápida cuando el Developer ya terminó.",
        steps=[PackStep("qa", chain_from_previous=False)],
    ),
    "discovery": PackDefinition(
        id="discovery",
        name="Pack Discovery",
        description="Functional + Technical en modo exploración / feasibility.",
        steps=[
            PackStep("functional", chain_from_previous=False),
            PackStep("technical"),
        ],
    ),
    "hotfix": PackDefinition(
        id="hotfix",
        name="Pack Hotfix",
        description="Technical (bug) → Developer → QA (regresión). Salta Functional.",
        steps=[
            PackStep("technical", chain_from_previous=False),
            PackStep("developer"),
            PackStep("qa"),
        ],
    ),
    "refactor": PackDefinition(
        id="refactor",
        name="Pack Refactor",
        description="Technical (análisis) → Developer (iso-functional) → QA (regresión).",
        steps=[
            PackStep("technical", chain_from_previous=False),
            PackStep("developer"),
            PackStep("qa"),
        ],
    ),
}


def list_packs() -> list[dict]:
    return [p.to_dict() for p in PACKS.values()]


def get_pack(pack_id: str) -> PackDefinition | None:
    return PACKS.get(pack_id)
