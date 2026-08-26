"""Stage 1 Agno routing agent — full Algorithm 1 pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

from skillreducer.config import Config, resolve_api_key
from skillreducer.llm.agno_client import AgnoLLMClient
from skillreducer.model import create_routing_model
from skillreducer.models import LlmUsage, Skill
from skillreducer.stage1.compress import compress_description
from skillreducer.stage1.generate import generate_description
from skillreducer.stage1.oracle import (
    Stage1Oracle,
    build_stage1_oracle,
    simulated_oracle,
)
from skillreducer.stage1.prompts import (
    GENERATE_FROM_BODY_PROMPT,
    STAGE1_DESCRIPTION,
    STAGE1_INSTRUCTIONS,
)
from skillreducer.tokenizer import count_tokens

try:
    from agno.agent import Agent
except ImportError:  # pragma: no cover
    Agent = None  # type: ignore[misc, assignment]


@dataclass
class Stage1Result:
    """Output of Stage 1 routing-layer optimization on one skill."""

    description: str
    notes: list[str] = field(default_factory=list)
    generated: bool = False
    compressed: bool = False


def create_stage1_routing_agent(config: Config) -> Agent:
    """Create the Agno routing model agent used for O(d,Q,C) oracle calls.

    Stage 1 Phase 1: routing model that selects the target skill from pool C.
    """
    if Agent is None:
        raise ImportError("agno is not installed. Install with: pip install agno")
    if not resolve_api_key(config):
        raise ValueError(
            "API key required. Set api_key in .env or environment, or in config.yaml."
        )

    return Agent(
        name="skillreducer-stage1-routing",
        model=create_routing_model(config),
        description=STAGE1_DESCRIPTION,
        instructions=STAGE1_INSTRUCTIONS,
        markdown=False,
        telemetry=False,
    )


class Stage1RoutingAgent:
    """Stage 1 pipeline backed by a dedicated Agno routing agent.

    Implements Gao et al. 2026 Algorithm 1:
      1. Generate description if missing or <= threshold tokens
      2. Build oracle context (Q, TF-IDF distractors, adversarial s_adv)
      3. Segment description into semantic clauses U
      4. DDMIN with simulated routing oracle O(d,Q,C)
      5. Oracle-gated paraphrase + polish
      6. Phase 2 validation on Q_val with selective restore / fallback
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self._agent = create_stage1_routing_agent(self.config)
        self._llm = AgnoLLMClient(self._agent)

    @property
    def agent(self) -> Agent:
        """Underlying Agno routing agent."""
        return self._agent

    @property
    def llm(self) -> AgnoLLMClient:
        """LLM adapter wrapping the routing agent."""
        return self._llm

    @property
    def usage(self) -> LlmUsage:
        """Accumulated routing-agent LLM token usage."""
        usage = getattr(self._llm, "usage", None)
        return usage if isinstance(usage, LlmUsage) else LlmUsage()

    def build_oracle(
        self,
        skill: Skill,
        skill_library: list[Skill] | None = None,
    ) -> Stage1Oracle:
        """Assemble Stage 1 oracle context Q, C (distractors + s_adv) for one skill."""
        return build_stage1_oracle(skill, self._llm, self.config, skill_library)

    def generate(
        self,
        skill: Skill,
        oracle_ctx: Stage1Oracle | None = None,
    ) -> str:
        """Generate a routing description from skill body; validate via O(d,Q,C).

        Stage 1 pre-compression for missing or short (<=40 token) descriptions.
        """
        ctx = oracle_ctx or self.build_oracle(skill)
        result = self._llm.complete_json(
            GENERATE_FROM_BODY_PROMPT.format(
                skill_name=skill.name,
                body=skill.body[:8000],
            )
        )
        if isinstance(result, dict) and result.get("description"):
            candidate = str(result["description"]).strip()
            if simulated_oracle(candidate, ctx, self._llm):
                return candidate
        return generate_description(skill, self._llm, oracle_ctx=ctx, config=self.config)

    def routing_oracle(
        self,
        description: str,
        oracle_ctx: Stage1Oracle,
        *,
        phase2: bool = False,
    ) -> bool:
        """Evaluate O(d,Q,C) on a candidate description (Phase 1 or Phase 2 Q_val)."""
        queries = oracle_ctx.q_val if phase2 and oracle_ctx.q_val else None
        return simulated_oracle(description, oracle_ctx, self._llm, queries=queries)

    def compress(
        self,
        description: str,
        skill: Skill,
        oracle_ctx: Stage1Oracle | None = None,
        skill_library: list[Skill] | None = None,
    ) -> tuple[str, list[str]]:
        """Compress description via DDMIN + O(d,Q,C) + Phase 2 validation."""
        ctx = oracle_ctx or self.build_oracle(skill, skill_library)
        ctx.original_description = description.strip()
        return compress_description(
            description,
            self._llm,
            skill=skill,
            oracle_ctx=ctx,
            skill_library=skill_library,
            max_restore_steps=self.config.max_restore_steps,
            config=self.config,
        )

    def run(
        self,
        skill: Skill,
        skill_library: list[Skill] | None = None,
    ) -> Stage1Result:
        """Execute full Stage 1 on a parsed skill; returns optimized description."""
        notes: list[str] = []
        description = skill.description.strip()
        generated = False
        compressed = False
        oracle_ctx = self.build_oracle(skill, skill_library)

        if not description or count_tokens(description) <= self.config.short_description_tokens:
            description = self.generate(skill, oracle_ctx=oracle_ctx)
            generated = True
            notes.append("Stage 1: generated description from body")
            oracle_ctx.original_description = description

        if description:
            new_desc, compress_notes = self.compress(
                description,
                skill,
                oracle_ctx=oracle_ctx,
                skill_library=skill_library,
            )
            notes.extend(compress_notes)
            if new_desc != description:
                compressed = True
            description = new_desc

        return Stage1Result(
            description=description,
            notes=notes,
            generated=generated,
            compressed=compressed,
        )
