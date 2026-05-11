"""
ConstitutionalKernel — Immutable axioms that sit on a separate execution plane.

Properties:
- Axioms never decay
- Cannot be altered except through formal amendment process
- All amendments are logged via the audit kernel (Chronicle)
- Provides constitutional validity checks on beliefs

Phase 3.3: Delegates to ConstitutionalGate for plugin-based validation.
"""
from typing import List, Optional, Dict
from datetime import datetime, timezone

from Weaver_ASI.constitutional.axioms import DEFAULT_AXIOMS
from Weaver_ASI.constitutional.gate import ConstitutionalGate


class ConstitutionalKernel:
    """Manages the constitutional axioms and their enforcement."""

    def __init__(self, audit_log=None):
        """
        Args:
            audit_log: Optional Chronicle-like object for logging amendments
        """
        self.audit_log = audit_log
        self.axioms: List[str] = []
        self._amendment_log: List[Dict] = []

    def load_defaults(self) -> None:
        """Load default axioms."""
        self.axioms = list(DEFAULT_AXIOMS)
        self._log_amendment("load_defaults", "Loaded default axioms", "SYSTEM")

    def add_axiom(self, text: str, agent: str = "SYSTEM") -> None:
        """Add a new axiom. Logs the amendment via the audit kernel."""
        if text in self.axioms:
            raise ValueError(f"Axiom already exists: {text}")
        self.axioms.append(text)
        self._log_amendment("add_axiom", text, agent)

    def remove_axiom(self, text: str, agent: str = "SYSTEM") -> None:
        """Remove an axiom. Logs the amendment."""
        if text not in self.axioms:
            raise ValueError(f"Axiom not found: {text}")
        self.axioms.remove(text)
        self._log_amendment("remove_axiom", text, agent)

    def get_axioms(self) -> List[str]:
        """Get a copy of all current axioms."""
        return list(self.axioms)

    def is_valid(self, belief_text: str) -> bool:
        """Check if a belief is valid according to current axioms AND plugins.

        Phase 3.3: Delegates to ConstitutionalGate for plugin validation
        in addition to axiom checks.
        """
        # 1. Check built-in axioms (heuristic negation match)
        if self._contradicts_any_axiom(belief_text):
            return False
        # 2. Check registered plugin validators
        return ConstitutionalGate.validate(belief_text)

    def _contradicts_any_axiom(self, belief_text: str) -> bool:
        """Return True if the belief contradicts any axiom."""
        for axiom in self.axioms:
            if self._might_violate(axiom, belief_text):
                return True
        return False

    def check_axiom_compliance(self, belief_text: str) -> List[str]:
        """Check which axioms a belief might violate.

        Returns:
            List of axiom texts that the belief potentially violates
        """
        violations = []
        belief_lower = belief_text.lower()

        for axiom in self.axioms:
            if self._might_violate(axiom, belief_lower):
                violations.append(axiom)

        return violations

    def _might_violate(self, axiom: str, belief: str) -> bool:
        """Heuristic check for potential axiom violations."""
        # Check for direct negation of axiom concepts
        negations = ['not ', 'no ', 'never ', 'without ', 'forged ', 'hallucination ']
        axiom_lower = axiom.lower()

        for neg in negations:
            if belief.startswith(neg) and neg in axiom_lower:
                return True

        # Check for concepts that directly contradict axioms
        axiom_concepts = {
            'cryptographic': ['unverified', 'unsigned', 'unproven'],
            'provenance': ['forged', 'fabricated', 'untraceable'],
            'trust': ['automatically restore', 'blind trust'],
            'graceful': ['panic', 'crash', 'unhandled'],
        }

        for concept, bad_patterns in axiom_concepts.items():
            if concept in axiom_lower:
                for pattern in bad_patterns:
                    if pattern in belief:
                        return True

        return False

    def _log_amendment(self, action: str, details: str, agent: str) -> None:
        """Log an axiom amendment."""
        amendment = {
            'timestamp': datetime.now(timezone.utc).timestamp(),
            'action': action,
            'details': details,
            'agent': agent,
        }
        self._amendment_log.append(amendment)

        # If audit log is available, emit a constitutional_axiom event
        if self.audit_log:
            try:
                self.audit_log.append({
                    'type': 'constitutional_axiom',
                    'action': action,
                    'details': details,
                    'agent': agent,
                })
            except Exception:
                pass  # Gracefully handle if audit log doesn't support this

    def get_amendment_log(self) -> List[Dict]:
        """Get the log of all axiom amendments."""
        return list(self._amendment_log)

    def axiom_count(self) -> int:
        """Get the number of axioms."""
        return len(self.axioms)
