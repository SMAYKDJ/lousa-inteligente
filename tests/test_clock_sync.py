"""Testes da estimativa de diferença de relógio (latência ponta a ponta)."""

import pytest

from desktop.communication.clock_sync import ClockSync


def test_no_samples_no_estimate():
    sync = ClockSync()
    assert sync.estimate is None and sync.to_local_ms(100.0) is None


def test_symmetric_link_recovers_offset():
    # Celular adiantado 5000 ms; 10 ms de ida e 10 de volta.
    sync = ClockSync()
    sync.add_sample(t_sent_ms=1000.0, t_reply_ms=6010.0, t_received_ms=1020.0)
    assert sync.estimate.offset_ms == pytest.approx(5000.0)
    assert sync.estimate.uncertainty_ms == pytest.approx(10.0)
    assert sync.to_local_ms(7000.0) == pytest.approx(2000.0)


def test_lowest_rtt_sample_wins():
    sync = ClockSync()
    sync.add_sample(1000.0, 6010.0, 1020.0)  # RTT 20, offset 5000
    sync.add_sample(2000.0, 7090.0, 2100.0)  # RTT 100, assimétrico: offset 5040
    assert sync.estimate.offset_ms == pytest.approx(5000.0)


def test_window_forgets_old_samples():
    sync = ClockSync(window=2)
    sync.add_sample(0.0, 5001.0, 2.0)  # RTT 2 (a melhor), sai da janela depois
    sync.add_sample(10.0, 5015.0, 20.0)
    sync.add_sample(30.0, 5035.0, 40.0)
    assert sync.estimate.uncertainty_ms == pytest.approx(5.0)


def test_negative_rtt_is_ignored():
    sync = ClockSync()
    sync.add_sample(100.0, 5.0, 90.0)
    assert sync.estimate is None
