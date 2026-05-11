#!/usr/bin/env python3
"""
test_steward_override.py — Steward override tests
==================================================
Phase 4: Tests for steward tooling and override capabilities.
"""
import sys
import os
import secrets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.crypto.steward_registry import StewardKey, StewardRegistry
from kernel.tooling.steward_tooling import StewardTooling, StewardOrchestrator
from kernel.core.event import Intent


def test_steward_signing():
    """Test steward signing of amendments."""
    print("\n[TEST 1] Steward signing...")
    key = StewardKey(
        steward_id="TEST_STEWARD",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    tooling = StewardTooling(key, registry)

    attest = tooling.sign_amendment("test_node_001", "Test amendment")
    assert attest is not None
    assert attest.steward_id == "TEST_STEWARD"
    assert attest.action == "AMENDMENT_SIGN"
    assert len(attest.signature) == 64
    print(f"  ✓ Signed amendment: {attest.justification[:40]}...")


def test_steward_checkpoint_signing():
    """Test steward signing of checkpoints."""
    print("\n[TEST 2] Checkpoint signing...")
    key = StewardKey(
        steward_id="TEST_STEWARD",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    tooling = StewardTooling(key, registry)

    attest = tooling.sign_checkpoint("evt_checkpoint_001")
    assert attest is not None
    assert attest.action == "CHECKPOINT_NOTARIZE"
    assert attest.steward_id == "TEST_STEWARD"
    print(f"  ✓ Signed checkpoint notarization")


def test_steward_override_intent():
    """Test steward override intent creation."""
    print("\n[TEST 3] Override intent creation...")
    key = StewardKey(
        steward_id="STEWARD_OVERRIDE_TEST",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    orchestrator = StewardOrchestrator(key, registry)
    intent = orchestrator.tooling.create_override_intent("System verified safe", step=10)

    assert isinstance(intent, Intent)
    assert intent.action == "STEWARD_OVERRIDE"
    assert intent.agent == "STEWARD_OVERRIDE_TEST"
    assert intent.attestation is not None
    assert "justification" in intent.attestation
    print(f"  ✓ Override intent created with attestation")


def test_steward_audit_log():
    """Test steward audit logging."""
    print("\n[TEST 4] Audit log...")
    key = StewardKey(
        steward_id="AUDIT_STEWARD",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    tooling = StewardTooling(key, registry)

    # Perform several actions
    tooling.sign_amendment("node1", "Amendment 1")
    tooling.sign_checkpoint("ckpt1")
    tooling.sign_amendment("node2", "Amendment 2")

    log = tooling.get_audit_log()
    assert len(log) == 3, f"Expected 3 log entries, got {len(log)}"
    assert tooling.get_signature_count() == 3
    print(f"  ✓ Audit log: {len(log)} entries, {tooling.get_signature_count()} signatures")


def test_steward_orchestrator():
    """Test steward orchestrator integration."""
    print("\n[TEST 5] Steward orchestrator...")
    key = StewardKey(
        steward_id="ORCHESTRATOR_STEWARD",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    orchestrator = StewardOrchestrator(key, registry)

    attest = orchestrator.apply_amendment_chain(
        description="Add new kernel feature",
        parents=[],
        version=1,
        author="admin",
    )
    assert attest is not None
    assert attest.action == "AMENDMENT_SIGN"
    print(f"  ✓ Orchestrator applied amendment: {attest.justification[:40]}...")

    # Notarize a checkpoint
    cp_attest = orchestrator.notarize_checkpoint("evt_001_checkpoint")
    assert cp_attest is not None
    assert cp_attest.action == "CHECKPOINT_NOTARIZE"
    print(f"  ✓ Orchestrator notarized checkpoint")


def test_amendment_signature_verification():
    """Test amendment signature verification."""
    print("\n[TEST 6] Signature verification...")
    key = StewardKey(
        steward_id="VERIFY_STEWARD",
        public_key_hex=secrets.token_hex(32),
    )
    registry = StewardRegistry()
    registry.register(key)

    tooling = StewardTooling(key, registry)

    # Sign an amendment
    attest = tooling.sign_amendment("verify_node", "Verification test")

    # Verify the signature
    # Note: verify_amendment_signature checks payload_hash consistency
    # Since we're verifying our own signature, it should pass
    assert tooling.verify_amendment_signature(attest), "Own signature should verify"
    print("  ✓ Steward signature verified")


def test_multiple_stewards():
    """Test multiple stewards in same registry."""
    print("\n[TEST 7] Multiple stewards...")
    registry = StewardRegistry()

    key1 = StewardKey(steward_id="STEWARD_1", public_key_hex=secrets.token_hex(32))
    key2 = StewardKey(steward_id="STEWARD_2", public_key_hex=secrets.token_hex(32))
    registry.register(key1)
    registry.register(key2)

    tooling1 = StewardTooling(key1, registry)
    tooling2 = StewardTooling(key2, registry)

    attest1 = tooling1.sign_amendment("node1", "Steward 1 amendment")
    attest2 = tooling2.sign_amendment("node2", "Steward 2 amendment")

    assert attest1.steward_id == "STEWARD_1"
    assert attest2.steward_id == "STEWARD_2"
    assert attest1.signature != attest2.signature, "Different stewards should have different signatures"
    print("  ✓ Multiple stewards produce distinct signatures")


def main():
    tests = [
        test_steward_signing,
        test_steward_checkpoint_signing,
        test_steward_override_intent,
        test_steward_audit_log,
        test_steward_orchestrator,
        test_amendment_signature_verification,
        test_multiple_stewards,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'═'*60}")
    print(f"  Steward Override Tests: {passed} passed, {failed} failed")
    print(f"{'═'*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
