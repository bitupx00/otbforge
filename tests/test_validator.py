"""
Tests for ai_core.map_validator — MapValidator, ValidationIssue, helpers.

Minimum 15 tests covering all 13 checks plus summary and edge-cases.
"""

from __future__ import annotations

import pytest

from ai_core.otbm_types import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TownData,
    WaypointData,
)
from ai_core.map_validator import MapValidator, ValidationIssue, _container_depth


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_tile(x: int = 100, y: int = 100, z: int = 7, ground_id: int = 102,
               house_id: int = 0, items: list | None = None) -> TileData:
    return TileData(x=x, y=y, z=z, ground_id=ground_id, house_id=house_id,
                    items=items or [])


def _make_item(id_: int = 3756, children: list | None = None) -> ItemData:
    return ItemData(id=id_, children=children or [])


def _make_map(width: int = 2048, height: int = 2048,
              tiles: list | None = None, towns: list | None = None,
              waypoints: list | None = None, spawns: list | None = None,
              npc_spawns: list | None = None) -> MapData:
    return MapData(
        width=width, height=height,
        tiles=tiles or [],
        towns=towns or [],
        waypoints=waypoints or [],
        spawns=spawns or [],
        npc_spawns=npc_spawns or [],
    )


# ------------------------------------------------------------------
# ValidationIssue dataclass
# ------------------------------------------------------------------

class TestValidationIssue:
    def test_valid_severities(self) -> None:
        for sev in ("error", "warning", "info"):
            issue = ValidationIssue(sev, "cat", "msg")
            assert issue.severity == sev

    def test_invalid_severity_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid severity"):
            ValidationIssue("critical", "cat", "msg")  # type: ignore[arg-type]

    def test_optional_position(self) -> None:
        issue = ValidationIssue("info", "cat", "msg", position=(1, 2, 3))
        assert issue.position == (1, 2, 3)
        issue2 = ValidationIssue("info", "cat", "msg")
        assert issue2.position is None


# ------------------------------------------------------------------
# Container depth helper
# ------------------------------------------------------------------

class TestContainerDepth:
    def test_leaf_depth(self) -> None:
        assert _container_depth(_make_item()) == 0

    def test_one_level(self) -> None:
        parent = _make_item(children=[_make_item()])
        assert _container_depth(parent) == 1

    def test_nested(self) -> None:
        innermost = _make_item()
        mid = _make_item(children=[innermost])
        outer = _make_item(children=[mid])
        assert _container_depth(outer) == 2


# ------------------------------------------------------------------
# 1. Valid map → 0 issues
# ------------------------------------------------------------------

class TestValidMap:
    def test_valid_map_no_issues(self) -> None:
        tile = _make_tile()
        spawn = SpawnData(x=100, y=100, z=7, radius=5,
                          monsters=[("Rat", 0, 0)])
        town = TownData(id=1, name="Main", temple=Position(100, 100, 7))
        npc = NPCSpawnData(x=100, y=100, z=7, npc_name="Guide")
        wp = WaypointData(name="temple", pos=Position(100, 100, 7))
        m = _make_map(tiles=[tile], towns=[town], waypoints=[wp],
                      spawns=[spawn], npc_spawns=[npc])
        issues = MapValidator.validate(m)
        assert len(issues) == 0

    def test_empty_map_warning(self) -> None:
        m = _make_map()
        issues = MapValidator.validate(m)
        cats = [i.severity for i in issues]
        assert "warning" in cats
        assert any("empty" in i.message.lower() for i in issues)


# ------------------------------------------------------------------
# 2. Dimensions
# ------------------------------------------------------------------

class TestDimensions:
    def test_zero_width(self) -> None:
        issues = MapValidator.check_dimensions(_make_map(width=0))
        assert any(i.severity == "error" and "width" in i.message for i in issues)

    def test_negative_height(self) -> None:
        issues = MapValidator.check_dimensions(_make_map(height=-1))
        assert any(i.severity == "error" and "height" in i.message for i in issues)

    def test_large_map_info(self) -> None:
        issues = MapValidator.check_dimensions(_make_map(width=4096, height=4096))
        assert any(i.severity == "info" for i in issues)

    def test_exceeds_max_dim(self) -> None:
        issues = MapValidator.check_dimensions(_make_map(width=65536))
        assert any(i.severity == "error" and "exceeds" in i.message for i in issues)


# ------------------------------------------------------------------
# 3. Tiles bounds
# ------------------------------------------------------------------

class TestTilesBounds:
    def test_out_of_bounds_tile(self) -> None:
        tile = _make_tile(x=3000, y=100)
        m = _make_map(width=2048, tiles=[tile])
        issues = MapValidator.check_tiles_bounds(m)
        assert any(i.severity == "error" and "out of" in i.message for i in issues)

    def test_in_bounds_tile_ok(self) -> None:
        tile = _make_tile(x=100, y=100)
        issues = MapValidator.check_tiles_bounds(_make_map(tiles=[tile]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# 4. Ground IDs
# ------------------------------------------------------------------

class TestGroundIds:
    def test_zero_ground_warning(self) -> None:
        tile = _make_tile(ground_id=0)
        issues = MapValidator.check_ground_ids(_make_map(tiles=[tile]))
        assert any(i.severity == "warning" and "no ground" in i.message for i in issues)


# ------------------------------------------------------------------
# 5. Duplicate tiles
# ------------------------------------------------------------------

class TestDuplicateTiles:
    def test_duplicate_tiles_error(self) -> None:
        t1 = _make_tile()
        t2 = _make_tile()
        issues = MapValidator.check_no_duplicate_tiles(_make_map(tiles=[t1, t2]))
        assert any(i.severity == "error" and "Duplicate" in i.message for i in issues)

    def test_unique_tiles_ok(self) -> None:
        t1 = _make_tile(x=100, y=100)
        t2 = _make_tile(x=101, y=100)
        issues = MapValidator.check_no_duplicate_tiles(_make_map(tiles=[t1, t2]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# 6. Tile items valid
# ------------------------------------------------------------------

class TestTileItemsValid:
    def test_invalid_item_id(self) -> None:
        item = _make_item(id_=0)
        tile = _make_tile(items=[item])
        issues = MapValidator.check_tile_items_valid(_make_map(tiles=[tile]))
        assert any(i.severity == "error" and "invalid id" in i.message for i in issues)


# ------------------------------------------------------------------
# 7. Container depth
# ------------------------------------------------------------------

class TestContainerDepth:
    def test_deep_containers_warning(self) -> None:
        # depth 4 → exceeds limit of 3
        d0 = _make_item()
        d1 = _make_item(children=[d0])
        d2 = _make_item(children=[d1])
        d3 = _make_item(children=[d2])
        d4 = _make_item(children=[d3])
        tile = _make_tile(items=[d4])
        issues = MapValidator.check_container_depth(_make_map(tiles=[tile]))
        assert any(i.severity == "warning" and "depth" in i.message for i in issues)

    def test_shallow_containers_ok(self) -> None:
        child = _make_item()
        parent = _make_item(children=[child])
        tile = _make_tile(items=[parent])
        issues = MapValidator.check_container_depth(_make_map(tiles=[tile]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# 8. House tiles
# ------------------------------------------------------------------

class TestHouseTiles:
    def test_house_without_towns_warning(self) -> None:
        tile = _make_tile(house_id=42)
        issues = MapValidator.check_house_tiles_valid(_make_map(tiles=[tile]))
        assert any(i.severity == "warning" and "no towns" in i.message for i in issues)

    def test_house_with_towns_ok(self) -> None:
        tile = _make_tile(house_id=42)
        town = TownData(id=1, name="City")
        issues = MapValidator.check_house_tiles_valid(
            _make_map(tiles=[tile], towns=[town]))
        assert len(issues) == 0

    def test_negative_house_id_error(self) -> None:
        tile = _make_tile(house_id=-1)
        issues = MapValidator.check_house_tiles_valid(_make_map(tiles=[tile]))
        assert any(i.severity == "error" and "Negative" in i.message for i in issues)


# ------------------------------------------------------------------
# 9 & 10. Spawns
# ------------------------------------------------------------------

class TestSpawns:
    def test_spawn_out_of_bounds(self) -> None:
        spawn = SpawnData(x=5000, y=5000, z=7, radius=5,
                          monsters=[("Rat", 0, 0)])
        issues = MapValidator.check_spawns_bounds(_make_map(spawns=[spawn]))
        assert any(i.severity == "error" and "out of" in i.message for i in issues)

    def test_empty_spawn_monsters_error(self) -> None:
        spawn = SpawnData(x=100, y=100, z=7, radius=5, monsters=[])
        issues = MapValidator.check_spawn_monsters(_make_map(spawns=[spawn]))
        assert any(i.severity == "error" and "no monsters" in i.message for i in issues)

    def test_spawn_with_monsters_ok(self) -> None:
        spawn = SpawnData(x=100, y=100, z=7, radius=5,
                          monsters=[("Rat", 0, 0), ("Snake", 1, 1)])
        issues = MapValidator.check_spawn_monsters(_make_map(spawns=[spawn]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# 11. Towns unique
# ------------------------------------------------------------------

class TestTownsUnique:
    def test_duplicate_town_ids_error(self) -> None:
        t1 = TownData(id=1, name="City")
        t2 = TownData(id=1, name="Village")
        issues = MapValidator.check_towns_unique(_make_map(towns=[t1, t2]))
        assert any(i.severity == "error" and "Duplicate" in i.message for i in issues)

    def test_unique_towns_ok(self) -> None:
        t1 = TownData(id=1, name="City")
        t2 = TownData(id=2, name="Village")
        issues = MapValidator.check_towns_unique(_make_map(towns=[t1, t2]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# 12. Waypoints unique
# ------------------------------------------------------------------

class TestWaypointsUnique:
    def test_duplicate_waypoints_warning(self) -> None:
        w1 = WaypointData(name="temple", pos=Position(100, 100, 7))
        w2 = WaypointData(name="temple", pos=Position(200, 200, 7))
        issues = MapValidator.check_waypoints_unique(
            _make_map(waypoints=[w1, w2]))
        assert any(i.severity == "warning" and "Duplicate" in i.message for i in issues)


# ------------------------------------------------------------------
# 13. NPC spawns bounds
# ------------------------------------------------------------------

class TestNPCSpawns:
    def test_npc_out_of_bounds_error(self) -> None:
        npc = NPCSpawnData(x=5000, y=5000, z=7, npc_name="Guide")
        issues = MapValidator.check_npc_spawns_bounds(
            _make_map(npc_spawns=[npc]))
        assert any(i.severity == "error" and "out of" in i.message for i in issues)

    def test_npc_in_bounds_ok(self) -> None:
        npc = NPCSpawnData(x=100, y=100, z=7, npc_name="Guide")
        issues = MapValidator.check_npc_spawns_bounds(
            _make_map(npc_spawns=[npc]))
        assert len(issues) == 0


# ------------------------------------------------------------------
# Combined valid map (terrain + city + spawns → 0 errors)
# ------------------------------------------------------------------

class TestCombinedValidMap:
    def test_combined_valid_map_no_errors(self) -> None:
        """A realistic map with terrain tiles, a town, spawns, NPC, waypoints."""
        tiles = [
            _make_tile(x=0, y=0, z=7, ground_id=102),    # grass
            _make_tile(x=1, y=0, z=7, ground_id=103),    # dirt
            _make_tile(x=0, y=1, z=7, ground_id=102, house_id=1),
        ]
        towns = [TownData(id=1, name="Main City", temple=Position(0, 0, 7))]
        waypoints = [
            WaypointData(name="dp", pos=Position(1, 0, 7)),
            WaypointData(name="temple", pos=Position(0, 0, 7)),
        ]
        spawns = [
            SpawnData(x=50, y=50, z=7, radius=10,
                      monsters=[("Rat", 0, 0), ("Spider", 2, -1)]),
        ]
        npcs = [NPCSpawnData(x=0, y=0, z=7, npc_name="Banker")]
        m = _make_map(tiles=tiles, towns=towns, waypoints=waypoints,
                      spawns=spawns, npc_spawns=npcs)
        issues = MapValidator.validate(m)
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0, f"Unexpected errors: {errors}"


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

class TestSummary:
    def test_summary_counts(self) -> None:
        issues = [
            ValidationIssue("error", "tiles", "bad tile", (1, 2, 3)),
            ValidationIssue("error", "tiles", "another bad tile", (4, 5, 6)),
            ValidationIssue("warning", "spawns", "meh", (7, 8, 9)),
            ValidationIssue("info", "dimensions", "big map"),
        ]
        s = MapValidator.summary(issues)
        assert s == {"errors": 2, "warnings": 1, "info": 1}

    def test_summary_empty(self) -> None:
        assert MapValidator.summary([]) == {"errors": 0, "warnings": 0, "info": 0}
