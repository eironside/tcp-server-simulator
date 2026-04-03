import pytest

from tcp_sim.engine.scheduler import SendScheduler


@pytest.mark.unit
def test_scheduler_start_stop_placeholder() -> None:
    scheduler = SendScheduler()
    scheduler.start()
    assert scheduler.is_running is True
    scheduler.stop()
    assert scheduler.is_running is False
