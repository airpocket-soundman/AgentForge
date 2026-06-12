"""Proactive stall watch decision (pure) — VISION 柱5 / workers.html §3(b)."""
from app.reception.service import _TIMEOUT_FORCE_STOP_N, _silence_health, _stall_decision


def test_health_is_silence_based_not_total_time():
    # A long-but-alive build stays "progressing": only SILENCE matters, so project
    # size / gate-revision rounds never get mis-judged as a stall.
    assert _silence_health("codegen", 30) == "progressing"   # heartbeat 30s ago
    assert _silence_health("codegen", 500) == "slow"          # past 480s budget
    assert _silence_health("codegen", 800) == "stuck"         # past budget×1.5
    assert _silence_health("planning", 200) == "slow"         # FLASH budget 150s
    assert _silence_health("receiving", 100) == "progressing"


def test_healthy_run_does_nothing():
    assert _stall_decision("progressing", False, 0) == "none"


def test_first_stall_prompts():
    assert _stall_decision("slow", False, 0) == "prompt"
    assert _stall_decision("stuck", False, 0) == "prompt"


def test_pending_prompt_suppresses_reprompt():
    # While the ①②③ question awaits an answer, the watch stays quiet.
    assert _stall_decision("stuck", True, 1) == "none"


def test_second_stall_force_stops():
    # After ②wait reset the clock, the next judgment is #2 = N → force stop.
    assert _TIMEOUT_FORCE_STOP_N == 2
    assert _stall_decision("slow", False, 1) == "force_stop"
