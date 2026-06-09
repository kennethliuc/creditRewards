"""Benchmarks load from bundled data directory (Docker + pip install)."""

from __future__ import annotations

from credit_rewards.benchmarks import BENCHMARKS_PATH, load_program_benchmarks


def test_benchmarks_path_uses_data_dir():
    assert BENCHMARKS_PATH.name == "program_benchmarks.yaml"
    assert BENCHMARKS_PATH.exists()
    assert "reference" in BENCHMARKS_PATH.parts


def test_load_program_benchmarks_includes_utilization_fields():
    benchmarks = load_program_benchmarks()
    amex = benchmarks["American Express Membership Rewards"]
    assert amex["cpp_portal"] == 2.0
    assert amex["utilization_weights"] == [0.5, 0.35, 0.15]
