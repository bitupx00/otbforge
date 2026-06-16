"""Tests for OTBM writer + reader roundtrip."""

from __future__ import annotations

import os
import tempfile
from dataclasses import replace

import pytest

from ai_core.otbm_types import (
    Attr,
    ESCAPE,
    NODE_END,
    NODE_START,
    OTBM_MAGIC,
    NodeType,
    Position,
    TileFlags,
    Tiles,
    ItemData,
    MapData,
    NPCSpawnData,
    SpawnData,
    TileData,
    TownData,
    WaypointData,
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


def _make_minimal_map() -> MapData:
    return MapData(
        width=256,
        height=256,
        description="Test Map",
    )


# ---------------------------------------------------------------------------
# Basic magic & structure
# ---------------------------------------------------------------------------

class TestMagicAndStructure:

    def test_magic_bytes(self):
        raw = OTBMWriter(_make_minimal_map()).write()
        assert raw[:4] == OTBM_MAGIC

    def test_root_node(self):
        raw = OTBMWriter(_make_minimal_map()).write()
        assert raw[4] == NODE_START
        assert raw[5] == NodeType.ROOTV1

    def test_map_data_node(self):
        raw = OTBMWriter(_make_minimal_map()).write()
        # after header: MAP_DATA starts
        assert NODE_START in raw

    def test_empty_map_roundtrip(self):
        m = _make_minimal_map()
        result = _roundtrip(m)
        assert result.width == m.width
        assert result.height == m.height
        assert result.description == m.description
        assert result.otbm_version == 2
        assert result.otb_major_version == 2
        assert result.otb_minor_version == 7


# ---------------------------------------------------------------------------
# Tile roundtrip
# ---------------------------------------------------------------------------

class TestTileRoundtrip:

    def test_single_ground_tile(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(x=100, y=50, z=7, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        t = result.tiles[0]
        assert t.x == 100
        assert t.y == 50
        assert t.z == 7
        assert t.ground_id == Tiles.GRASS
        assert t.items == []

    def test_multiple_tiles(self):
        m = _make_minimal_map()
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
        m = _make_minimal_map()
        m.tiles = [
            TileData(x=10, y=10, z=7, ground_id=Tiles.GRASS),
            TileData(x=10, y=10, z=6, ground_id=Tiles.ROCK),
            TileData(x=10, y=10, z=0, ground_id=Tiles.STONE),
        ]
        result = _roundtrip(m)
        tiles_by_z = {t.z: t.ground_id for t in result.tiles}
        assert tiles_by_z == {7: Tiles.GRASS, 6: Tiles.ROCK, 0: Tiles.STONE}

    def test_all_ground_types(self):
        ground_ids = [Tiles.GRASS, Tiles.DIRT, Tiles.SAND, Tiles.WATER,
                      Tiles.LAVA, Tiles.SNOW, Tiles.ROCK, Tiles.STONE]
        m = _make_minimal_map()
        for i, gid in enumerate(ground_ids):
            m.tiles.append(TileData(x=i, y=0, z=7, ground_id=gid))
        result = _roundtrip(m)
        result_ids = sorted(t.ground_id for t in result.tiles)
        assert sorted(ground_ids) == result_ids


# ---------------------------------------------------------------------------
# Item roundtrip
# ---------------------------------------------------------------------------

class TestItemRoundtrip:

    def test_stacked_items(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=10, y=10, z=7,
            ground_id=Tiles.GRASS,
            items=[
                ItemData(id=Tiles.CHEST),
                ItemData(id=Tiles.WOOD),
            ],
        ))
        result = _roundtrip(m)
        t = result.tiles[0]
        assert len(t.items) == 2
        item_ids = sorted(i.id for i in t.items)
        assert item_ids == sorted([Tiles.CHEST, Tiles.WOOD])

    def test_item_with_count(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, count=42)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].count == 42

    def test_item_with_action_id(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, action_id=1234)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].action_id == 1234

    def test_item_with_unique_id(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, unique_id=999)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].unique_id == 999

    def test_item_with_text(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, text="Hello, Tibia!")],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].text == "Hello, Tibia!"

    def test_item_with_description(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, description="A magical item")],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].description == "A magical item"

    def test_item_with_charges(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, charges=50)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].charges == 50

    def test_item_with_teleport_dest(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.GRASS,
            items=[ItemData(
                id=Tiles.TELEPORT,
                teleport_dest=Position(x=1000, y=2000, z=5),
            )],
        ))
        result = _roundtrip(m)
        dest = result.tiles[0].items[0].teleport_dest
        assert dest is not None
        assert dest.x == 1000
        assert dest.y == 2000
        assert dest.z == 5

    def test_item_with_house_door_id(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=Tiles.CLOSED_DOOR, house_door_id=3)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].house_door_id == 3

    def test_item_with_depot_id(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(id=100, depot_id=5)],
        ))
        result = _roundtrip(m)
        assert result.tiles[0].items[0].depot_id == 5

    def test_container_with_children(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            items=[ItemData(
                id=Tiles.CHEST,
                children=[
                    ItemData(id=2160, count=1),  # gold coin
                    ItemData(id=2160, count=5),
                ],
            )],
        ))
        result = _roundtrip(m)
        chest = result.tiles[0].items[0]
        assert chest.id == Tiles.CHEST
        assert len(chest.children) == 2
        assert chest.children[0].id == 2160
        assert chest.children[0].count == 1
        assert chest.children[1].count == 5

    def test_nested_containers(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
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


# ---------------------------------------------------------------------------
# Tile flags
# ---------------------------------------------------------------------------

class TestTileFlags:

    def test_protection_zone(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.GRASS,
            flags=TileFlags.PROTECTIONZONE,
        ))
        result = _roundtrip(m)
        assert result.tiles[0].flags == TileFlags.PROTECTIONZONE

    def test_pvp_zone(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.GRASS,
            flags=TileFlags.PVPZONE,
        ))
        result = _roundtrip(m)
        assert result.tiles[0].flags & TileFlags.PVPZONE

    def test_combined_flags(self):
        flags = TileFlags.PROTECTIONZONE | TileFlags.NOLOGOUTZONE
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.GRASS,
            flags=flags,
        ))
        result = _roundtrip(m)
        assert result.tiles[0].flags == flags


# ---------------------------------------------------------------------------
# House tiles
# ---------------------------------------------------------------------------

class TestHouseTiles:

    def test_house_tile(self):
        m = _make_minimal_map()
        m.tiles.append(TileData(
            x=5, y=5, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            house_id=42,
        ))
        result = _roundtrip(m)
        assert result.tiles[0].house_id == 42


# ---------------------------------------------------------------------------
# Towns
# ---------------------------------------------------------------------------

class TestTowns:

    def test_single_town(self):
        m = _make_minimal_map()
        m.towns = [
            TownData(id=1, name="Carlin", temple=Position(x=100, y=100, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.towns) == 1
        assert result.towns[0].id == 1
        assert result.towns[0].name == "Carlin"
        assert result.towns[0].temple.x == 100
        assert result.towns[0].temple.y == 100
        assert result.towns[0].temple.z == 7

    def test_multiple_towns(self):
        m = _make_minimal_map()
        m.towns = [
            TownData(id=1, name="Carlin", temple=Position(x=100, y=100, z=7)),
            TownData(id=2, name="Thais", temple=Position(x=200, y=200, z=7)),
            TownData(id=3, name="Venore", temple=Position(x=300, y=300, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.towns) == 3
        names = {t.name for t in result.towns}
        assert names == {"Carlin", "Thais", "Venore"}


# ---------------------------------------------------------------------------
# Waypoints
# ---------------------------------------------------------------------------

class TestWaypoints:

    def test_single_waypoint(self):
        m = _make_minimal_map()
        m.waypoints = [
            WaypointData(name="dp", pos=Position(x=50, y=50, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.waypoints) == 1
        assert result.waypoints[0].name == "dp"
        assert result.waypoints[0].pos.x == 50

    def test_multiple_waypoints(self):
        m = _make_minimal_map()
        m.waypoints = [
            WaypointData(name="town", pos=Position(x=100, y=100, z=7)),
            WaypointData(name="hunt", pos=Position(x=500, y=300, z=7)),
        ]
        result = _roundtrip(m)
        assert len(result.waypoints) == 2
        assert result.waypoints[1].name == "hunt"
        assert result.waypoints[1].pos.y == 300


# ---------------------------------------------------------------------------
# Spawns
# ---------------------------------------------------------------------------

class TestSpawns:

    def test_single_spawn(self):
        m = _make_minimal_map()
        m.spawns = [
            SpawnData(
                x=100, y=100, z=7, radius=5,
                monsters=[("Rat", 0, 0)],
            ),
        ]
        result = _roundtrip(m)
        assert len(result.spawns) == 1
        s = result.spawns[0]
        assert s.x == 100
        assert s.radius == 5
        assert len(s.monsters) == 1
        assert s.monsters[0][0] == "Rat"

    def test_spawn_multiple_monsters(self):
        m = _make_minimal_map()
        m.spawns = [
            SpawnData(
                x=200, y=200, z=7, radius=10,
                monsters=[
                    ("Dragon", 2, 3),
                    ("Demon", 5, 1),
                    ("Orc", 0, 5),
                ],
            ),
        ]
        result = _roundtrip(m)
        s = result.spawns[0]
        assert len(s.monsters) == 3
        assert s.monsters[1][0] == "Demon"
        assert s.monsters[1][1] == 5
        assert s.monsters[1][2] == 1


# ---------------------------------------------------------------------------
# NPC spawns
# ---------------------------------------------------------------------------

class TestNPCSpawns:

    def test_npc_spawn(self):
        m = _make_minimal_map()
        m.npc_spawns = [
            NPCSpawnData(x=50, y=50, z=7, npc_name="Banker"),
        ]
        result = _roundtrip(m)
        assert len(result.spawns) == 1  # NPCs written as spawns
        s = result.spawns[0]
        assert s.x == 50
        assert s.y == 50
        assert s.radius == 1
        assert len(s.monsters) == 1
        assert s.monsters[0][0] == "Banker"


# ---------------------------------------------------------------------------
# Escape handling
# ---------------------------------------------------------------------------

class TestEscapedBytes:

    def test_large_item_ids_are_escaped(self):
        """Item IDs >= 0xFC (252) need escape in the wire format."""
        m = _make_minimal_map()
        # Use IDs that contain bytes >= 0xFC
        m.tiles.append(TileData(x=0, y=0, z=7, ground_id=0xFD))  # 253
        m.tiles.append(TileData(x=1, y=0, z=7, ground_id=0xFE))  # 254
        m.tiles.append(TileData(x=2, y=0, z=7, ground_id=0xFF))  # 255
        result = _roundtrip(m)
        ids = sorted(t.ground_id for t in result.tiles)
        assert ids == [0xFD, 0xFE, 0xFF]

    def test_large_coordinates(self):
        """Tiles at high coordinates that produce offsets >= 0xFC."""
        m = MapData(width=1000, height=1000, description="Big")
        m.tiles.append(TileData(x=511, y=511, z=7, ground_id=Tiles.GRASS))
        result = _roundtrip(m)
        assert len(result.tiles) == 1
        assert result.tiles[0].x == 511
        assert result.tiles[0].y == 511


# ---------------------------------------------------------------------------
# File save/load
# ---------------------------------------------------------------------------

class TestFileSaveLoad:

    def test_save_and_load(self, tmp_path):
        m = _make_minimal_map()
        m.tiles = [
            TileData(x=10, y=20, z=7, ground_id=Tiles.GRASS,
                     items=[ItemData(id=Tiles.CHEST)]),
        ]
        m.towns = [TownData(id=1, name="Test", temple=Position(x=50, y=50, z=7))]
        m.waypoints = [WaypointData(name="wp", pos=Position(x=100, y=100, z=7))]

        path = str(tmp_path / "test.otbm")
        writer = OTBMWriter(m)
        writer.save(path)

        assert os.path.exists(path)
        assert os.path.getsize(path) > 0

        loaded = OTBMReader.from_file(path)
        assert loaded.width == m.width
        assert loaded.height == m.height
        assert loaded.description == m.description
        assert len(loaded.tiles) == 1
        assert loaded.tiles[0].ground_id == Tiles.GRASS
        assert len(loaded.tiles[0].items) == 1
        assert loaded.tiles[0].items[0].id == Tiles.CHEST
        assert len(loaded.towns) == 1
        assert loaded.towns[0].name == "Test"
        assert len(loaded.waypoints) == 1
        assert loaded.waypoints[0].name == "wp"


# ---------------------------------------------------------------------------
# Complex integrated test
# ---------------------------------------------------------------------------

class TestComplexMap:

    def test_full_featured_map(self):
        """A map with a bit of everything."""
        m = MapData(
            width=1024,
            height=1024,
            description="AI Generated Dungeon",
        )
        # Ground tiles
        for x in range(5):
            for y in range(5):
                ground = Tiles.FLOOR_WOOD if y < 3 else Tiles.STONE_WALL
                m.tiles.append(TileData(x=100 + x, y=100 + y, z=7, ground_id=ground))

        # House tile
        m.tiles.append(TileData(
            x=100, y=100, z=7,
            ground_id=Tiles.FLOOR_WOOD,
            house_id=1,
            items=[
                ItemData(id=Tiles.CLOSED_DOOR, house_door_id=1),
            ],
        ))

        # Teleporter
        m.tiles.append(TileData(
            x=104, y=104, z=7,
            ground_id=Tiles.GRASS,
            items=[ItemData(
                id=Tiles.TELEPORT,
                teleport_dest=Position(x=200, y=200, z=6),
            )],
        ))

        # Town
        m.towns = [
            TownData(id=1, name="Dungeon Town", temple=Position(x=102, y=102, z=7)),
        ]

        # Waypoints
        m.waypoints = [
            WaypointData(name="entrance", pos=Position(x=100, y=100, z=7)),
            WaypointData(name="exit", pos=Position(x=104, y=104, z=7)),
        ]

        # Spawn
        m.spawns = [
            SpawnData(
                x=102, y=102, z=7, radius=3,
                monsters=[("Skeleton", 1, 0), ("Ghost", 2, 2)],
            ),
        ]

        result = _roundtrip(m)
        assert len(result.tiles) == 27  # 25 ground + house + teleport
        assert len(result.towns) == 1
        assert result.towns[0].name == "Dungeon Town"
        assert len(result.waypoints) == 2
        assert len(result.spawns) == 1
        assert len(result.spawns[0].monsters) == 2

        # Find house tile
        house_tiles = [t for t in result.tiles if t.house_id == 1]
        assert len(house_tiles) == 1
        door = house_tiles[0].items[0]
        assert door.house_door_id == 1

        # Find teleport
        tele_tiles = [t for t in result.tiles if any(i.id == Tiles.TELEPORT for i in t.items)]
        assert len(tele_tiles) == 1
        tp = tele_tiles[0].items[0]
        assert tp.teleport_dest.x == 200
        assert tp.teleport_dest.z == 6
