import json

import pytest

from justice_sim.config import DataLoadError, load_data


@pytest.mark.unit
def test_load_data_without_schema(tmp_path, data_dict_factory):
    data = data_dict_factory()
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    loaded = load_data(path, validate_schema=False)
    assert loaded.version == "test"


@pytest.mark.unit
def test_load_data_rejects_non_object(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(DataLoadError):
        load_data(path, validate_schema=False)
