import pytest

from tcp_sim.engine.file_reader import FileReader


@pytest.mark.unit
def test_file_reader_placeholder_initializes() -> None:
    reader = FileReader()
    reader.initialize()
    assert reader.is_ready is True
