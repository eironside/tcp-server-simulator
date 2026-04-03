import json

import pytest

from tcp_sim.gui.log_panel import export_log_lines, filter_log_lines, load_log_lines


@pytest.mark.unit
def test_load_log_lines_limits_tail(tmp_path) -> None:
    log_path = tmp_path / "tcp-sim.log"
    lines = [f"line-{idx}" for idx in range(20)]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    loaded = load_log_lines(log_path, max_lines=5)
    assert loaded == ["line-15", "line-16", "line-17", "line-18", "line-19"]


@pytest.mark.unit
def test_filter_log_lines_by_level_and_search() -> None:
    entries = [
        json.dumps({"level": "INFO", "message": "server started"}),
        json.dumps({"level": "ERROR", "message": "send failed"}),
        "plain-text-line",
    ]

    filtered_level = filter_log_lines(entries, level_filter="ERROR")
    assert len(filtered_level) == 1
    assert "send failed" in filtered_level[0]

    filtered_search = filter_log_lines(entries, search_text="server")
    assert len(filtered_search) == 1
    assert "server started" in filtered_search[0]


@pytest.mark.unit
def test_export_log_lines_writes_output(tmp_path) -> None:
    destination = tmp_path / "export" / "filtered.log"
    export_log_lines(["a", "b"], destination)

    assert destination.exists()
    assert destination.read_text(encoding="utf-8") == "a\nb\n"
