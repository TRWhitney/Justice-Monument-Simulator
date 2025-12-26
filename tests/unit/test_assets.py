import pytest

from justice_sim.util.assets import resolve_npc_image_path


@pytest.mark.unit
def test_resolve_npc_image_path_returns_repo_relative_path(data_factory):
    data = data_factory()
    npc = data.npcs_by_id["npc1"]
    npc = npc.__class__(
        id=npc.id, name=npc.name, image="builtin/images/test.png", tags=npc.tags
    )
    path = resolve_npc_image_path(data, npc)
    assert path is not None
    assert str(path).endswith("builtin/images/test.png")
