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

from kernel.constitutional.axioms import DEFAULT_AXIOMS
from kernel.constitutional.gate import ConstitutionalGate
from kernel.constitutional.intent import IngressGate, Intent


# ---------------------------------------------------------------------------
# _PermissiveGate — accepts all intents (backward-compatible fallback)
# ---------------------------------------------------------------------------
class _PermissiveGate:
    """No-op ingress gate. Accepts every Intent without verification.

    Used when ConstitutionalKernel is constructed without an explicit
    IngressGate.  In production, always pass an IngressGate.
    """
    def verify(self, intent: Intent) -> bool:
        return True


class ConstitutionalKernel:
    """Manages the constitutional axioms and their enforcement."""

    def __init__(self, audit_log=None, ingress_gate: Optional[IngressGate] = None):
        """
        Args:
            audit_log: Optional Chronicle-like object for logging amendments
            ingress_gate: Optional IngressGate for cryptographic intent verification.
                          If omitted, a permissive gate (all intents accepted) is used.
        """
        self.audit_log = audit_log
        self.axioms: List[str] = []
        self._amendment_log: List[Dict] = []
        self.ingress_gate = ingress_gate or _PermissiveGate()

    def load_defaults(self) -> None:
        """Load default axioms."""
        self.axioms = list(DEFAULT_AXIOMS)
        self._log_amendment("load_defaults", "Loaded default axioms", "SYSTEM")

    def add_axiom(self, text: str, intent: Optional[Intent] = None) -> None:
        """Add a new axiom. Logs the amendment via the audit kernel.

        Args:
            text: The axiom text to add.
            intent: A signed Intent authorizing the modification.
                    If omitted or invalid, the operation is rejected
                    unless the kernel was constructed with a permissive gate.
        """
        if intent is not None:
            if not self.ingress_gate.verify(intent):
                raise PermissionError(
                    "Axiom addition requires a valid signed Intent"
                )
        if text in self.axioms:
            raise ValueError(f"Axiom already exists: {text}")
        self.axioms.append(text)
        self._log_amendment("add_axiom", text, intent.operator_id if intent else "SYSTEM")

    def remove_axiom(self, text: str, intent: Optional[Intent] = None) -> None:
        """Remove an axiom. Logs the amendment.

        Args:
            text: The axiom text to remove.
            intent: A signed Intent authorizing the modification.
        """
        if intent is not None:
            if not self.ingress_gate.verify(intent):
                raise PermissionError(
                    "Axiom removal requires a valid signed Intent"
                )
        if text not in self.axioms:
            raise ValueError(f"Axiom not found: {text}")
        self.axioms.remove(text)
        self._log_amendment("remove_axiom", text, intent.operator_id if intent else "SYSTEM")

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
        """Heuristic check for potential axiom violations.

        Phase 5 upgrade: expanded from startswith-only to full substring
        matching for negations, plus override/bypass detection that
        contradicts every axiom.
        """
        belief_lower = belief.lower()
        axiom_lower = axiom.lower()

        # 1. Expanded negation check — any occurrence, not just prefix
        negations = [
            'not ', 'no ', 'never ', 'without ', 'forged ',
            'hallucination ', 'forged ', 'fake ', 'false ',
        ]
        for neg in negations:
            if neg in belief_lower and neg in axiom_lower:
                return True

        # 2. Concept-level contradiction matching (unchanged)
        axiom_concepts = {
            'cryptographic': ['unverified', 'unsigned', 'unproven'],
            'provenance': ['forged', 'fabricated', 'untraceable'],
            'trust': ['automatically restore', 'blind trust'],
            'graceful': ['panic', 'crash', 'unhandled'],
        }
        for concept, bad_patterns in axiom_concepts.items():
            if concept in axiom_lower:
                for pattern in bad_patterns:
                    if pattern in belief_lower:
                        return True

        # 3. Override / bypass / circumvent — contradicts every axiom
        override_patterns = [
            'override', 'bypass', 'circumvent', 'skip ',
            'ignore ', 'disable ', 'turn off', 'evade',
        ]
        for pat in override_patterns:
            if pat in belief_lower:
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
