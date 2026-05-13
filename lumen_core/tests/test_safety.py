import pytest
from lumen_core.safety.phase_space_gate import PhaseSpaceGate

def test_normal():
    g = PhaseSpaceGate()
    assert g.evaluate(0.3, "h1").passed

def test_entry():
    g = PhaseSpaceGate()
    g.evaluate(0.9, "h1")
    assert g.evaluate(0.9, "h2").restricted

def test_recovery():
    g = PhaseSpaceGate()
    g.evaluate(0.9, "h1"); g.evaluate(0.9, "h2")
    for _ in range(9):
        g.evaluate(0.2, "s")
    assert not g.restricted

def test_reset():
    g = PhaseSpaceGate()
    g.evaluate(0.9, "h1"); g.evaluate(0.9, "h2")
    for _ in range(5): g.evaluate(0.2, "s")
    g.evaluate(0.9, "h3")
    assert g.evaluate(0.2, "s").restricted
