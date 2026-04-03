import pytest
import tracemalloc

from tcp_sim.engine.file_reader import FileReader


@pytest.mark.soak
def test_large_file_streaming_stability_baseline(tmp_path) -> None:
    data_path = tmp_path / "large.csv"

    with data_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("id,value\n")
        for idx in range(25000):
            handle.write(f"{idx},v{idx}\n")

    reader = FileReader(data_path, delimiter=",", has_header=True)

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    count = sum(1 for _ in reader.iter_valid_rows())

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    mem_before = sum(stat.size for stat in snapshot_before.statistics("filename"))
    mem_after = sum(stat.size for stat in snapshot_after.statistics("filename"))

    assert count == 25000
    assert mem_after - mem_before < 30_000_000
