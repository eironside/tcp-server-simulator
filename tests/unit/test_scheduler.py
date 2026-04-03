import pytest
import asyncio

from tcp_sim.engine.scheduler import ScheduledMessage, SendScheduler


@pytest.mark.unit
def test_scheduler_start_stop_and_step_loop() -> None:
    scheduler = SendScheduler(records=[b"a", b"b"], loop=True)
    scheduler.start()
    assert scheduler.is_running is True

    first = scheduler.step()
    second = scheduler.step()
    third = scheduler.step()

    assert first is not None and first.payload == b"a"
    assert second is not None and second.payload == b"b"
    assert third is not None and third.payload == b"a"

    scheduler.stop()
    assert scheduler.is_running is False


@pytest.mark.unit
def test_scheduler_jump_to_line() -> None:
    scheduler = SendScheduler(records=[b"1", b"2", b"3"], loop=False)
    scheduler.jump_to(3)
    message = scheduler.step()
    assert message is not None
    assert message.line_number == 3


@pytest.mark.unit
def test_scheduler_runtime_rate_update() -> None:
    scheduler = SendScheduler(records=[b"1"], rate_features_per_second=5.0)
    scheduler.set_rate(20.0)
    assert scheduler.rate_features_per_second == pytest.approx(20.0)


@pytest.mark.unit
def test_scheduler_file_swap_increments_generation_and_emits_header() -> None:
    scheduler = SendScheduler(records=[b"old"], loop=False)
    scheduler.request_file_swap([b"new"], header_payload=b"header")

    header = scheduler.step()
    message = scheduler.step()

    assert isinstance(header, ScheduledMessage)
    assert header.is_header is True
    assert header.payload == b"header"
    assert message is not None
    assert message.payload == b"new"
    assert message.generation == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scheduler_auto_mode_sends_messages() -> None:
    scheduler = SendScheduler(records=[b"a", b"b"], rate_features_per_second=100.0, loop=False)
    sent: list[ScheduledMessage] = []

    async def callback(message: ScheduledMessage) -> None:
        sent.append(message)
        if len(sent) >= 2:
            scheduler.stop()
        await asyncio.sleep(0)

    await scheduler.run_auto(callback)
    assert [item.payload for item in sent] == [b"a", b"b"]
