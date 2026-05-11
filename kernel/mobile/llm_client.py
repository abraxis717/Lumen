"""
llm_client.py — MobileModel → GovernedClaim adapter for oracle_agent.py

Wraps a MobileModel (GGUF) into the interface expected by OracleAgent:
    Callable[[str, str], List[GovernedClaim]]
    -> list of GovernedClaim objects.

Parsing prompt: instructs the model to return structured JSON so we can
extract text, confidence, and citations deterministically.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from kernel.council.claims import GovernedClaim

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_claims_from_text(text: str, agent: str) -> List[GovernedClaim]:
    """Parse a model-generated text block into GovernedClaim objects.

    The model is prompted to return JSON. If JSON parsing fails we fall
    back to heuristic extraction.
    """
    text = text.strip()

    # Try JSON parsing first (look for JSON array or object)
    json_matches = re.findall(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if json_matches:
        json_text = json_matches[0].strip()
    else:
        # Try to find a JSON array/object directly
        if text.startswith('['):
            json_text = text
        else:
            json_text = None

    if json_text:
        try:
            data = json.loads(json_text)
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = [data]
            else:
                items = None
        except json.JSONDecodeError:
            items = None

        if items:
            claims = []
            for item in items:
                if isinstance(item, dict):
                    claims.append(GovernedClaim(
                        text=item.get("claim", item.get("text", str(item))),
                        confidence=float(item.get("confidence", 0.85)),
                        citations=item.get("citations", []),
                        agent=agent,
                        metadata={"source": "gguf-model", "model_path": "N/A"},
                    ))
            if claims:
                return claims

    # Heuristic fallback: extract claim-like lines
    claims = []
    for line in text.splitlines():
        line = line.strip()
        # Skip code fences and empty lines
        if line.startswith("```") or not line:
            continue
        # Skip reasoning tags
        if line.startswith("</think>") or line.startswith("<think"):
            continue
        if len(line) > 10:
            claims.append(GovernedClaim(
                text=line,
                confidence=0.85,
                agent=agent,
                metadata={"source": "gguf-model", "model_path": "N/A"},
            ))

    return claims


# ---------------------------------------------------------------------------
# MobileModelLLMClient
# ---------------------------------------------------------------------------

class MobileModelLLMClient:
    """Adapt a MobileModel into the oracle_agent.py llm_client interface.

    Args:
        model: A MobileModel instance (already loaded).
        prompt_template: Optional custom prompt template.
        max_tokens: Maximum tokens per generation call.
        temperature: Sampling temperature override.
    """

    DEFAULT_PROMPT = (
        "You are an ASI oracle.  Propose governed claims about the "
        "current system state.\n\n"
        "Return your claims as a JSON array.  Each element must have:\n"
        '  "claim": "<claim text>",\n'
        '  "confidence": <float 0-1>,\n'
        '  "citations": [<optional node IDs>]\n\n'
        "Example:\n"
        '[{"claim": "Sensor reading nominal.", "confidence": 0.92, "citations": ["sensor_01"]}]'
    )

    def __init__(
        self,
        model: Any,  # MobileModel
        prompt_template: Optional[str] = None,
        max_tokens: int = 128,
        temperature: Optional[float] = None,
    ) -> None:
        self._model = model
        self._prompt_template = prompt_template or self.DEFAULT_PROMPT
        self._max_tokens = max_tokens
        self._temperature = temperature

    def __call__(self, prompt: str, *, agent_name: str = "Oracle") -> List[GovernedClaim]:
        """Generate claims from a prompt via the GGUF model.

        Args:
            prompt: The context prompt from OracleAgent._format_prompt().
            agent_name: Agent identifier for metadata.

        Returns:
            List[GovernedClaim] extracted from model output.
        """
        full_prompt = f"{self._prompt_template}\n\n{prompt}"

        try:
            generated = self._model.generate(
                full_prompt,
                max_tokens=self._max_tokens,
                temperature=self._temperature if self._temperature is not None else self._model.temperature,
            )
        except Exception as exc:
            logger.error("MobileModel.generate failed: %s", exc)
            return []

        claims = _parse_claims_from_text(generated, agent_name)
        if not claims:
            # Last resort: treat entire output as a single claim
            claims = [
                GovernedClaim(
                    text=generated.strip(),
                    confidence=0.70,
                    agent=agent_name,
                    metadata={"source": "gguf-model", "model_path": self._model.model_path},
                )
            ]

        return claims

    @property
    def model_path(self) -> str:
        return self._model.model_path
