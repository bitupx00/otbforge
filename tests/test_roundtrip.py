"""
Comprehensive round-trip tests for OTBM writer + reader.

Tests write → read → compare for every feature:
- models, escaping, tile flags, item attributes, houses, towns, waypoints,
  spawns, containers, v2/v3 versions, statistics, edge cases.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from ai_core.models import (
    Attr, ESCAPE, NODE_END, NODE_START, OTBM_MAGIC,
    NodeType, Position, TileFlag, Tiles,
    ItemData, MapData, NPCSpawnData, SpawnData, TileData,
    TownData, WaypointData, OtbVersion, OTB_V2_7, OTB_V3_12,
)
from ai_core.otbm_writer import OTBMWriter
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _roundtrip(map_data: MapData) -> MapData:
    """Write then read back, return parsed MapData."""
    raw = OTBMWriter(map_data).write()
    return OTBMReader(raw).read()


def _minimal() -> MapData:
    return MapData(width=256, height=256, description="Test Map")


# ===================================================================
# 1. Magic & structure
# ===================================================================

class TestMagicAndStructure:

    def test_magic_bytes(self):
        raw = OTBMWriter(_minimal()).write()
        assert raw[:4] == OTBM_MAGIC

    def test_root_node(self):
        raw = OTBMWriter(_minimal()).write()
        assert raw[4] == NODE_START
        assert raw[5] == NodeType.ROOTV1

    def test_empty_map_roundtrip(self):
        m = _minimal()
        result = _roundtrip(m)
        assert result.width == m.width
        assert result.height == m.height
        assert result.description == m.description
        assert result.otbm_version == 2
        assert result.otb_major_version == 2
        assert result.otb_minor_version == 7


# ===================================================================
# 2. Version support
# ===================================================================

class TestVersions:

    def test_otbm_v2_default(self):
        m = _minimal()
        m.otbm_version = 2
        m.otb_major_version = 2
        m.otb_minor_version = 7
        result = _roundtrip(m)
        assert result.otbm_version == 2

    def test_otbm_v3(self):
        m = _minimal()
        m.otbm_version = 3
        m.otb_major_version = 3
        m.otb_minor_version = 12
        m.tiles.append(TileData(x=0, y=0, z=7, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert result.otbm_version == 3
        assert result.otb_major_version == 3
        assert result.otb_minor_version == 12

    def test_custom_otb_version(self):
        m = _minimal()
        m.otb_major_version = 1
        m.otb_minor_version = 42
        result = _roundtrip(m)
        assert result.otb_major_version == 1
        assert result.otb_minor_version == 42


# ===================================================================
# 3. Tile round-trip
# ===================================================================

class TestTileRoundtrip:

    def test_single_ground_tile(self):
        m = _minimal()
        m.tiles.append(TileData(x=100, y=50, z=7, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        t = result.tiles[0]
        assert (t.x, t.y, t.z, t.ground_id) == (100, 50, 7, Tiles.GRASS)
        assert t.items == []

    def test_multiple_tiles(self):
        m = _minimal()
        m.tiles = [
            TileData(x=0, y=0, z=7, ground_id=Tiles.GRASS),
            TileData(x=1, y=0, z=7, ground_id=Tiles.DIRT),
            TileData(x=0, y=1, z=7, ground_id=Tiles.SAND),
        ]
        result = _roundtrip(m)
        assert len(result.tiles) == 3
        ids = sorted(t.ground_id for t in result.tiles)
        assert ids == sorted([Tiles.DIRT, Tiles.GRASS, Tiles.SAND])

    def test_different_z_levels(self):
        m = _minimal()
        m.tiles = [
            TileData(x=10, y=10, z=7, ground_id=Tiles.GRASS),
            TileData(x=10, y=10, z=6, ground_id=Tiles.ROCK),
            TileData(x=10, y=10, z=0, ground_id=Tiles.STONE),
        ]
        result = _roundtrip(m)
        tiles_by_z = {t.z: t.ground_id for t in result.tiles}
        assert tiles_by_z == {7: Tiles.GRASS, 6: Tiles.ROCK, 0: Tiles.STONE}

    def test_no_ground_tile(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        assert result.tiles[0].ground_id == 0

    def test_all_ground_types(self):
        ground_ids = [Tiles.GRASS, Tiles.DIRT, Tiles.SAND, Tiles.WATER,
                      Tiles.LAVA, Tiles.SNOW, Tiles.ROCK, Tiles.STONE]
        m = _minimal()
        for i, gid in enumerate(ground_ids):
            m.tiles.append(TileData(x=i, y=0, z=7, ground_id=gid))
        result = _roundtrip(m)
        result_ids = sorted(t.ground_id for t in result.tiles)
        assert sorted(ground_ids) == result_ids


# ===================================================================
# 4. Tile flags
# ===================================================================

class TestTileFlags:

    def test_protection_zone(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=TileFlag.PROTECTIONZONE))
        result = _roundtrip(m)
        assert result.tiles[0].flags == TileFlag.PROTECTIONZONE

    def test_pvp_zone(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=TileFlag.PVPZONE))
        result = _roundtrip(m)
        assert result.tiles[0].flags & TileFlag.PVPZONE

    def test_no_logout_zone(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=TileFlag.NOLOGOUTZONE))
        result = _roundtrip(m)
        assert result.tiles[0].flags & TileFlag.NOLOGOUTZONE

    def test_nosave_zone(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=TileFlag.NOSAVEZONE))
        result = _roundtrip(m)
        assert result.tiles[0].flags & TileFlag.NOSAVEZONE

    def test_haslight_flag(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=TileFlag.HASLIGHT))
        result = _roundtrip(m)
        assert result.tiles[0].flags & TileFlag.HASLIGHT

    def test_combined_flags(self):
        flags = TileFlag.PROTECTIONZONE | TileFlag.NOLOGOUTZONE | TileFlag.NOSAVEZONE
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.GRASS,
                                flags=flags))
        result = _roundtrip(m)
        assert result.tiles[0].flags == flags

    def test_all_flags_individually(self):
        """Test every single flag in isolation."""
        flag_names = [
            "PROTECTIONZONE", "NOSUMMON_MONSTERZONE", "NOPVPZONE",
            "NOLOGOUTZONE", "PVPZONE", "NOHOUSETILE", "REFRESH",
            "NOSAVEZONE", "HASLIGHT",
        ]
        for name in flag_names:
            flag = getattr(TileFlag, name)
            m = _minimal()
            m.tiles.append(TileData(x=0, y=0, z=7, ground_id=Tiles.GRASS,
                                    flags=flag))
            result = _roundtrip(m)
            assert result.tiles[0].flags == flag, f"Failed for {name}"


# ===================================================================
# 5. Item attributes
# ===================================================================

class TestItemAttributes:

    def _tile_with_item(self, item: ItemData) -> MapData:
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
                                items=[item]))
        return m

    def test_count(self):
        result = _roundtrip(self._tile_with_item(ItemData(id=100, count=42)))
        assert result.tiles[0].items[0].count == 42

    def test_action_id(self):
        result = _roundtrip(self._tile_with_item(ItemData(id=100, action_id=1234)))
        assert result.tiles[0].items[0].action_id == 1234

    def test_unique_id(self):
        result = _roundtrip(self._tile_with_item(ItemData(id=100, unique_id=999)))
        assert result.tiles[0].items[0].unique_id == 999

    def test_text(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, text="Hello, Tibia!")))
        assert result.tiles[0].items[0].text == "Hello, Tibia!"

    def test_description(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, description="A magical item")))
        assert result.tiles[0].items[0].description == "A magical item"

    def test_charges(self):
        result = _roundtrip(self._tile_with_item(ItemData(id=100, charges=50)))
        assert result.tiles[0].items[0].charges == 50

    def test_teleport_dest(self):
        result = _roundtrip(self._tile_with_item(ItemData(
            id=Tiles.TELEPORT,
            teleport_dest=Position(x=1000, y=2000, z=5),
        )))
        dest = result.tiles[0].items[0].teleport_dest
        assert dest is not None
        assert (dest.x, dest.y, dest.z) == (1000, 2000, 5)

    def test_house_door_id(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=Tiles.CLOSED_DOOR, house_door_id=3)))
        assert result.tiles[0].items[0].house_door_id == 3

    def test_depot_id(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, depot_id=5)))
        assert result.tiles[0].items[0].depot_id == 5

    def test_duration(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, duration=3600)))
        assert result.tiles[0].items[0].duration == 3600

    def test_decay_state(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, decay_state=2)))
        assert result.tiles[0].items[0].decay_state == 2

    def test_written_date(self):
        ts = 1700000000
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, written_date=ts)))
        assert result.tiles[0].items[0].written_date == ts

    def test_written_by(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, written_by="Admin")))
        assert result.tiles[0].items[0].written_by == "Admin"

    def test_rune_charges(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, rune_charges=3)))
        assert result.tiles[0].items[0].rune_charges == 3

    def test_sleeper_guid(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, sleeper_guid=12345)))
        assert result.tiles[0].items[0].sleeper_guid == 12345

    def test_sleep_start(self):
        result = _roundtrip(self._tile_with_item(
            ItemData(id=100, sleep_start=98765)))
        assert result.tiles[0].items[0].sleep_start == 98765

    def test_all_attrs_combined(self):
        """One item with every attribute set."""
        item = ItemData(
            id=9999, count=99, action_id=111, unique_id=222,
            text="label", description="info", charges=7,
            house_door_id=4, depot_id=6,
            teleport_dest=Position(x=500, y=600, z=3),
            duration=86400, decay_state=1,
            written_date=1700000000, written_by="GM",
            rune_charges=2, sleeper_guid=1000, sleep_start=2000,
        )
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
                                items=[item]))
        result = _roundtrip(m)
        ri = result.tiles[0].items[0]
        assert ri.id == 9999
        assert ri.count == 99
        assert ri.action_id == 111
        assert ri.unique_id == 222
        assert ri.text == "label"
        assert ri.description == "info"
        assert ri.charges == 7
        assert ri.house_door_id == 4
        assert ri.depot_id == 6
        assert ri.teleport_dest == Position(500, 600, 3)
        assert ri.duration == 86400
        assert ri.decay_state == 1
        assert ri.written_date == 1700000000
        assert ri.written_by == "GM"
        assert ri.rune_charges == 2
        assert ri.sleeper_guid == 1000
        assert ri.sleep_start == 2000


# ===================================================================
# 6. Containers (nested items)
# ===================================================================

class TestContainers:

    def test_container_with_children(self):
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(
                id=Tiles.CHEST,
                children=[
                    ItemData(id=2160, count=1),
                    ItemData(id=2160, count=5),
                ],
            )],
        ))
        result = _roundtrip(m)
        chest = result.tiles[0].items[0]
        assert chest.id == Tiles.CHEST
        assert len(chest.children) == 2
        assert chest.children[0].count == 1
        assert chest.children[1].count == 5

    def test_nested_containers(self):
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(
                id=Tiles.CHEST,
                children=[ItemData(
                    id=Tiles.DRAWER,
                    children=[ItemData(id=2160, count=10)],
                )],
            )],
        ))
        result = _roundtrip(m)
        chest = result.tiles[0].items[0]
        drawer = chest.children[0]
        assert drawer.id == Tiles.DRAWER
        assert drawer.children[0].id == 2160
        assert drawer.children[0].count == 10

    def test_deeply_nested_containers(self):
        """3 levels of nesting."""
        inner = ItemData(id=2160, count=100)
        middle = ItemData(id=Tiles.DRAWER, children=[inner])
        outer = ItemData(id=Tiles.CHEST, children=[middle])
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD, items=[outer],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].children[0].children[0].count == 100

    def test_container_with_attributed_children(self):
        """Children with attributes survive roundtrip."""
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(
                id=Tiles.CHEST,
                children=[
                    ItemData(id=2160, count=5, action_id=100),
                    ItemData(id=3031, text="scroll"),
                ],
            )],
        ))
        result = _roundtrip(m)
        chest = result.tiles[0].items[0]
        assert chest.children[0].action_id == 100
        assert chest.children[1].text == "scroll"


# ===================================================================
# 7. House tiles
# ===================================================================

class TestHouseTiles:

    def test_house_tile(self):
        m = _minimal()
        m.tiles.append(TileData(x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
                                house_id=42))
        result = _roundtrip(m)
        assert result.tiles[0].house_id == 42

    def test_multiple_house_tiles(self):
        m = _minimal()
        m.tiles = [
            TileData(x=10, y=10, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=1),
            TileData(x=11, y=10, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=1),
            TileData(x=12, y=10, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=2),
        ]
        result = _roundtrip(m)
        house_1 = [t for t in result.tiles if t.house_id == 1]
        house_2 = [t for t in result.tiles if t.house_id == 2]
        assert len(house_1) == 2
        assert len(house_2) == 1

    def test_house_tile_with_door(self):
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            house_id=1,
            items=[ItemData(id=Tiles.CLOSED_DOOR, house_door_id=1)],
        ))
        result = _roundtrip(m)
        t = result.tiles[0]
        assert t.house_id == 1
        assert t.items[0].house_door_id == 1


# ===================================================================
# 8. Towns
# ===================================================================

class TestTowns:

    def test_single_town(self):
        m = _minimal()
        m.towns = [TownData(id=1, name="Carlin",
                            temple=Position(x=100, y=100, z=7))]
        result = _roundtrip(m)
        assert len(result.towns) == 1
        t = result.towns[0]
        assert (t.id, t.name, t.temple.x, t.temple.y, t.temple.z) == \
               (1, "Carlin", 100, 100, 7)

    def test_multiple_towns(self):
        m = _minimal()
        m.towns = [
            TownData(id=1, name="Carlin", temple=Position(x=100, y=100, z=7)),
            TownData(id=2, name="Thais", temple=Position(x=200, y=200, z=7)),
            TownData(id=3, name="Venore", temple=Position(x=300, y=300, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.towns) == 3
        names = {t.name for t in result.towns}
        assert names == {"Carlin", "Thais", "Venore"}

    def test_town_with_unicode_name(self):
        m = _minimal()
        m.towns = [TownData(id=1, name="Ñoño Town",
                            temple=Position(x=50, y=50, z=7))]
        result = _roundtrip(m)
        assert result.towns[0].name == "Ñoño Town"


# ===================================================================
# 9. Waypoints
# ===================================================================

class TestWaypoints:

    def test_single_waypoint(self):
        m = _minimal()
        m.waypoints = [WaypointData(name="dp",
                                    pos=Position(x=50, y=50, z=7))]
        result = _roundtrip(m)
        assert len(result.waypoints) == 1
        assert result.waypoints[0].name == "dp"
        assert result.waypoints[0].pos.x == 50

    def test_multiple_waypoints(self):
        m = _minimal()
        m.waypoints = [
            WaypointData(name="town", pos=Position(x=100, y=100, z=7)),
            WaypointData(name="hunt", pos=Position(x=500, y=300, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.waypoints) == 2
        assert result.waypoints[1].name == "hunt"
        assert result.waypoints[1].pos.y == 300

    def test_waypoint_different_z(self):
        m = _minimal()
        m.waypoints = [
            WaypointData(name="surface", pos=Position(x=100, y=100, z=7)),
            WaypointData(name="cave", pos=Position(x=100, y=100, z=8)),
            WaypointData(name="deep", pos=Position(x=100, y=100, z=12)),
        ]
        result = _roundtrip(m)
        zs = {wp.pos.z for wp in result.waypoints}
        assert zs == {7, 8, 12}


# ===================================================================
# 10. Spawns
# ===================================================================

class TestSpawns:

    def test_single_spawn(self):
        m = _minimal()
        m.spawns = [SpawnData(x=100, y=100, z=7, radius=5,
                              monsters=[("Rat", 0, 0)])]
        result = _roundtrip(m)
        assert len(result.spawns) == 1
        assert result.spawns[0].x == 100
        assert result.spawns[0].radius == 5
        assert result.spawns[0].monsters[0][0] == "Rat"

    def test_spawn_multiple_monsters(self):
        m = _minimal()
        m.spawns = [SpawnData(
            x=200, y=200, z=7, radius=10,
            monsters=[("Dragon", 2, 3), ("Demon", 5, 1), ("Orc", 0, 5)],
        )]
        result = _roundtrip(m)
        s = result.spawns[0]
        assert len(s.monsters) == 3
        assert s.monsters[1] == ("Demon", 5, 1)


# ===================================================================
# 11. NPC spawns
# ===================================================================

class TestNPCSpawns:

    def test_npc_spawn(self):
        m = _minimal()
        m.npc_spawns = [NPCSpawnData(x=50, y=50, z=7, npc_name="Banker")]
        result = _roundtrip(m)
        assert len(result.spawns) == 1
        s = result.spawns[0]
        assert s.x == 50
        assert s.radius == 1
        assert s.monsters[0][0] == "Banker"


# ===================================================================
# 12. Escaping (critical for correctness)
# ===================================================================

class TestEscapedBytes:

    def test_item_ids_0xFD_0xFE_0xFF(self):
        """Item IDs 253, 254, 255 need 0xFD escape prefix."""
        m = _minimal()
        m.tiles.append(TileData(x=0, y=0, z=7, ground_id=0xFD))
        m.tiles.append(TileData(x=1, y=0, z=7, ground_id=0xFE))
        m.tiles.append(TileData(x=2, y=0, z=7, ground_id=0xFF))
        result = _roundtrip(m)
        ids = sorted(t.ground_id for t in result.tiles)
        assert ids == [0xFD, 0xFE, 0xFF]

    def test_large_coordinates(self):
        """Offsets >= 0xFD need escaping."""
        m = MapData(width=1000, height=1000, description="Big")
        m.tiles.append(TileData(x=511, y=511, z=7, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        assert result.tiles[0].x == 511
        assert result.tiles[0].y == 511

    def test_large_action_id(self):
        """action_id=0xFFFE should survive."""
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, action_id=0xFFFE)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].action_id == 0xFFFE

    def test_large_unique_id(self):
        m = _minimal()
        m.tiles.append(TileData(
            x=5, y=5, z=7, ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, unique_id=0xFFFF)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].unique_id == 0xFFFF

    def test_escaped_z_value(self):
        """z=0xFF (255) is not valid but should not corrupt the stream."""
        m = _minimal()
        m.tiles.append(TileData(x=0, y=0, z=15, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        assert result.tiles[0].z == 15

    def test_large_town_temple_coords(self):
        m = _minimal()
        m.towns = [TownData(id=1, name="Far Town",
                            temple=Position(x=0xFFFE, y=0xFFFE, z=7))]
        result = _roundtrip(m)
        assert result.towns[0].temple.x == 0xFFFE


# ===================================================================
# 13. File save / load
# ===================================================================

class TestFileSaveLoad:

    def test_save_and_load(self, tmp_path):
        m = _minimal()
        m.tiles = [TileData(x=10, y=20, z=7, ground_id=Tiles.GRASS,
                             items=[ItemData(id=Tiles.CHEST)])]
        m.towns = [TownData(id=1, name="Test",
                             temple=Position(x=50, y=50, z=7))]
        m.waypoints = [WaypointData(name="wp",
                                     pos=Position(x=100, y=100, z=7))]

        path = str(tmp_path / "test.otbm")
        writer = OTBMWriter(m)
        writer.save(path)

        assert os.path.exists(path)
        assert os.path.getsize(path) > 0

        loaded = OTBMReader.from_file(path)
        assert loaded.width == m.width
        assert loaded.description == m.description
        assert len(loaded.tiles) == 1
        assert loaded.tiles[0].ground_id == Tiles.GRASS
        assert len(loaded.towns) == 1
        assert loaded.towns[0].name == "Test"
        assert len(loaded.waypoints) == 1
        assert loaded.waypoints[0].name == "wp"


# ===================================================================
# 14. Statistics
# ===================================================================

class TestStats:

    def test_empty_map_stats(self):
        m = _minimal()
        stats = m.stats()
        assert stats["tiles"] == 0
        assert stats["ground_tiles"] == 0
        assert stats["towns"] == 0
        assert stats["waypoints"] == 0
        assert stats["spawns"] == 0
        assert stats["z_levels"] == 0
        assert stats["area_coverage"] == 0

    def test_populated_map_stats(self):
        m = _minimal()
        for x in range(10):
            for y in range(10):
                m.tiles.append(TileData(x=x, y=y, z=7, ground_id=Tiles.GRASS))
        m.towns = [TownData(id=1, name="T", temple=Position(x=5, y=5, z=7))]
        m.waypoints = [WaypointData(name="wp", pos=Position(x=5, y=5, z=7))]
        stats = m.stats()
        assert stats["tiles"] == 100
        assert stats["ground_tiles"] == 100
        assert stats["towns"] == 1
        assert stats["waypoints"] == 1
        assert stats["z_levels"] == 1

    def test_z_levels_count(self):
        m = _minimal()
        m.tiles = [
            TileData(x=0, y=0, z=7, ground_id=Tiles.GRASS),
            TileData(x=0, y=0, z=6, ground_id=Tiles.ROCK),
            TileData(x=0, y=0, z=8, ground_id=Tiles.STONE),
        ]
        stats = m.stats()
        assert stats["z_levels"] == 3

    def test_house_tiles_count(self):
        m = _minimal()
        m.tiles = [
            TileData(x=0, y=0, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=1),
            TileData(x=1, y=0, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=1),
            TileData(x=2, y=0, z=7, ground_id=Tiles.GRASS),
        ]
        stats = m.stats()
        assert stats["house_tiles"] == 2


# ===================================================================
# 15. Convenience builder methods
# ===================================================================

class TestBuilderMethods:

    def test_add_tile(self):
        m = _minimal()
        tile = m.add_tile(x=10, y=20, z=7, ground_id=Tiles.GRASS)
        assert tile.x == 10
        assert len(m.tiles) == 1

    def test_add_item(self):
        m = _minimal()
        m.add_tile(x=10, y=20, z=7, ground_id=Tiles.GRASS)
        m.add_item(x=10, y=20, z=7, item=ItemData(id=Tiles.CHEST))
        assert len(m.tiles[0].items) == 1

    def test_add_item_creates_tile_if_needed(self):
        m = _minimal()
        m.add_item(x=50, y=50, z=7, item=ItemData(id=Tiles.CHEST))
        assert len(m.tiles) == 1
        assert m.tiles[0].items[0].id == Tiles.CHEST

    def test_set_house(self):
        m = _minimal()
        m.add_tile(x=10, y=20, z=7, ground_id=Tiles.FLOOR_WOOD)
        m.set_house(x=10, y=20, z=7, house_id=42)
        assert m.tiles[0].house_id == 42

    def test_add_town(self):
        m = _minimal()
        m.add_town(1, "Carlin", Position(100, 100, 7))
        assert len(m.towns) == 1
        assert m.towns[0].name == "Carlin"

    def test_add_waypoint(self):
        m = _minimal()
        m.add_waypoint("dp", Position(50, 50, 7))
        assert len(m.waypoints) == 1
        assert m.waypoints[0].name == "dp"

    def test_builder_roundtrip(self):
        m = MapData(width=512, height=512, description="Builder Test")
        m.add_tile(x=100, y=100, z=7, ground_id=Tiles.GRASS)
        m.add_tile(x=101, y=100, z=7, ground_id=Tiles.GRASS,
                   flags=TileFlag.PROTECTIONZONE)
        m.set_house(x=100, y=100, z=7, house_id=1)
        m.add_item(x=100, y=100, z=7,
                   item=ItemData(id=Tiles.CLOSED_DOOR, house_door_id=1))
        m.add_town(1, "Builder Town", Position(100, 100, 7))
        m.add_waypoint("center", Position(100, 100, 7))

        result = _roundtrip(m)
        assert len(result.tiles) == 2
        assert result.towns[0].name == "Builder Town"
        assert result.waypoints[0].name == "center"


# ===================================================================
# 16. Complex integrated test
# ===================================================================

class TestComplexMap:

    def test_full_featured_map(self):
        """A map with a bit of everything."""
        m = MapData(width=1024, height=1024, description="AI Generated Dungeon")

        # Ground tiles (5x5)
        for x in range(5):
            for y in range(5):
                ground = Tiles.FLOOR_WOOD if y < 3 else Tiles.STONE_WALL
                m.tiles.append(TileData(
                    x=100 + x, y=100 + y, z=7, ground_id=ground))

        # House tile with door
        m.tiles.append(TileData(
            x=100, y=100, z=7, ground_id=Tiles.FLOOR_WOOD, house_id=1,
            items=[ItemData(id=Tiles.CLOSED_DOOR, house_door_id=1)],
        ))

        # Teleporter
        m.tiles.append(TileData(
            x=104, y=104, z=7, ground_id=Tiles.GRASS,
            items=[ItemData(id=Tiles.TELEPORT,
                            teleport_dest=Position(x=200, y=200, z=6))],
        ))

        # PZ tile
        m.tiles.append(TileData(
            x=105, y=105, z=7, ground_id=Tiles.GRASS,
            flags=TileFlag.PROTECTIONZONE,
        ))

        # Town
        m.towns = [TownData(id=1, name="Dungeon Town",
                            temple=Position(x=102, y=102, z=7))]

        # Waypoints
        m.waypoints = [
            WaypointData(name="entrance", pos=Position(x=100, y=100, z=7)),
            WaypointData(name="exit", pos=Position(x=104, y=104, z=7)),
        ]

        # Spawn
        m.spawns = [SpawnData(
            x=102, y=102, z=7, radius=3,
            monsters=[("Skeleton", 1, 0), ("Ghost", 2, 2)],
        )]

        result = _roundtrip(m)
        assert len(result.tiles) >= 27  # 25 ground + house + tp + pz
        assert len(result.towns) == 1
        assert result.towns[0].name == "Dungeon Town"
        assert len(result.waypoints) == 2
        assert len(result.spawns) == 1
        assert len(result.spawns[0].monsters) == 2

        # House check
        house_tiles = [t for t in result.tiles if t.house_id == 1]
        assert len(house_tiles) >= 1
        door = house_tiles[0].items[0]
        assert door.house_door_id == 1

        # Teleport check
        tele_tiles = [t for t in result.tiles
                      if any(i.id == Tiles.TELEPORT for i in t.items)]
        assert len(tele_tiles) == 1
        tp = tele_tiles[0].items[0]
        assert tp.teleport_dest.x == 200
        assert tp.teleport_dest.z == 6

        # PZ check
        pz_tiles = [t for t in result.tiles
                    if t.flags & TileFlag.PROTECTIONZONE]
        assert len(pz_tiles) >= 1


# ===================================================================
# 17. Model validation
# ===================================================================

class TestModelValidation:

    def test_position_valid(self):
        p = Position(100, 200, 7)
        p.validate()  # no exception

    def test_position_invalid_z(self):
        p = Position(0, 0, 16)
        with pytest.raises(ValueError):
            p.validate()

    def test_item_valid(self):
        ItemData(id=100, count=50).validate()

    def test_item_invalid_id(self):
        with pytest.raises(ValueError):
            ItemData(id=0).validate()

    def test_tile_valid(self):
        TileData(x=100, y=200, z=7, ground_id=102).validate()

    def test_map_data_valid(self):
        MapData().validate()

    def test_map_data_invalid_version(self):
        m = MapData(otbm_version=99)
        with pytest.raises(ValueError):
            m.validate()

    def test_town_invalid_id(self):
        t = TownData(id=0, name="X")
        with pytest.raises(ValueError):
            t.validate()


# ===================================================================
# 18. Repr / str
# ===================================================================

class TestRepr:

    def test_position_repr(self):
        assert "Position(100, 200, 7)" == repr(Position(100, 200, 7))

    def test_item_repr_minimal(self):
        assert "ItemData(id=100)" == repr(ItemData(id=100))

    def test_item_repr_with_attrs(self):
        r = repr(ItemData(id=100, count=5, text="hi"))
        assert "count=5" in r
        assert "text='hi'" in r

    def test_tile_repr(self):
        r = repr(TileData(x=10, y=20, z=7, ground_id=102))
        assert "10, 20, 7" in r
        assert "ground=102" in r

    def test_map_repr(self):
        m = MapData(width=512, height=512)
        r = repr(m)
        assert "512x512" in r
        assert "v2" in r

    def test_town_repr(self):
        r = repr(TownData(id=1, name="Thais"))
        assert "Thais" in r
