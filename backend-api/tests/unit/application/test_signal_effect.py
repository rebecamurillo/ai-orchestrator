"""`signal_effect` holds the effect types; `signal_effects` re-exports them."""

from __future__ import annotations

from orchestrator.application.use_cases import signal_effect, signal_effects


def test_the_effects_module_re_exports_the_same_objects() -> None:
    assert signal_effects.Effect is signal_effect.Effect
    assert signal_effects.CancelPlan is signal_effect.CancelPlan
    assert signal_effects.EffectFn is signal_effect.EffectFn
