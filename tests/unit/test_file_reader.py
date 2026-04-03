import pytest

from tcp_sim.engine.file_reader import FileReader


@pytest.mark.unit
def test_file_reader_preview_marks_invalid_rows(tmp_path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "id,value\n1,a\n2,b,extra\n3,c\n",
        encoding="utf-8",
    )

    reader = FileReader(data_path, delimiter=",", has_header=True)
    preview = reader.load_preview(limit=10)

    assert len(preview) == 3
    assert preview[0].valid is True
    assert preview[1].valid is False
    assert preview[2].valid is True


@pytest.mark.unit
def test_file_reader_scan_counts_invalid_rows(tmp_path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "id,value\n1,a\n2,b,extra\n3,c\n",
        encoding="utf-8",
    )

    reader = FileReader(data_path, delimiter=",", has_header=True)
    snapshot = reader.scan_file()

    assert snapshot.total_rows == 4
    assert snapshot.data_rows == 3
    assert snapshot.valid_rows == 2
    assert snapshot.invalid_rows == 1
    assert snapshot.completed is True


@pytest.mark.unit
def test_file_reader_iter_valid_rows_enforces_column_consistency(tmp_path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "id,value\n1,a\n2,b,extra\n3,c\n",
        encoding="utf-8",
    )

    reader = FileReader(data_path, delimiter=",", has_header=True)
    rows = list(reader.iter_valid_rows())

    assert [row.data_line_number for row in rows] == [1, 2]
    assert [row.fields for row in rows] == [["1", "a"], ["3", "c"]]


@pytest.mark.unit
def test_file_reader_supports_rfc_4180_quoted_fields(tmp_path) -> None:
    data_path = tmp_path / "quoted.csv"
    data_path.write_text(
        "id,text\n"
        "1,\"hello,world\"\n"
        "2,\"multi\nline\"\n",
        encoding="utf-8",
    )

    reader = FileReader(data_path, delimiter=",", has_header=True)
    rows = list(reader.iter_valid_rows())

    assert rows[0].fields[1] == "hello,world"
    assert rows[1].fields[1].replace("\r\n", "\n") == "multi\nline"


@pytest.mark.unit
def test_file_reader_background_scan_completes(tmp_path) -> None:
    data_path = tmp_path / "data.csv"
    data_path.write_text(
        "id,value\n1,a\n2,b\n",
        encoding="utf-8",
    )

    reader = FileReader(data_path, delimiter=",", has_header=True)
    reader.start_background_scan()
    assert reader.wait_for_scan(timeout=2.0) is True

    snapshot = reader.get_scan_snapshot()
    assert snapshot.completed is True
    assert snapshot.valid_rows == 2
