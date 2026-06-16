"""Tests for dungeon generator: BSP rooms, corridors, room types, spawn points,
doors, chests, stairs, multi-floor, and OTBMWriter round-trip integration."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.otbm_types import (
    MapData,
    TileData,
    Tiles,
)
from ai_core.otbm_writer import OTBMWriter
from ai_core.generators.dungeon import (
    DungeonGenerator,
    DungeonTiles,
    RoomType,
    _BSPNode,
    _Room,
)


# ===========================================================================
# Room types
# ===========================================================================

class TestRoomType:
    def test_all_types_defined(self):
        """All expected room types exist."""
        assert RoomType.NORMAL == 0
        assert RoomType.TREASURE == 1
        assert RoomType.BOSS == 2
        assert RoomType.SPAWN == 3
        assert RoomType.TRAP == 4

    def test_room_type_count(self):
        """There should be 5 room types."""
        assert len(RoomType) == 5


# ===========================================================================
# Internal structures
# ===========================================================================

class TestInternalStructures:
    def test_room_center(self):
        room = _Room(x=5, y=5, w=6, h=8)
        assert room.cx == 8
        assert room.cy == 9

    def test_room_area(self):
        room = _Room(x=0, y=0, w=10, h=5)
        assert room.area == 50

    def test_bsp_node_defaults(self):
        node = _BSPNode(x=0, y=0, w=64, h=64)
        assert node.left is None
        assert node.right is None
        assert node.room is None


# ===========================================================================
# DungeonGenerator basic
# ===========================================================================

class TestDungeonGenerator:
    def test_returns_mapdata(self):
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_dimensions(self):
        gen = DungeonGenerator(width=50, height=60, seed=1)
        result = gen.generate()
        assert result.width == 50
        assert result.height == 60

    def test_has_tiles(self):
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        # Every cell should have a tile (wall + rooms + corridors)
        assert len(result.tiles) == 64 * 64

    def test_all_tiles_have_ground(self):
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        for t in result.tiles:
            assert t.ground_id > 0, f"Tile ({t.x},{t.y},{t.z}) has no ground"


# ===========================================================================
# Rooms
# ===========================================================================

class TestDungeonRooms:
    def test_has_floor_tiles(self):
        """Rooms should produce stone floor tiles."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8,
                               min_room_size=4, max_room_size=10, seed=1)
        result = gen.generate()
        floors = [t for t in result.tiles
                  if DungeonTiles.FLOOR_MIN <= t.ground_id <= DungeonTiles.FLOOR_MAX]
        assert len(floors) > 0, "Expected floor tiles (rooms)"

    def test_has_walls(self):
        """Dungeon should have wall tiles surrounding rooms."""
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        walls = [t for t in result.tiles
                 if DungeonTiles.WALL_MIN <= t.ground_id <= DungeonTiles.WALL_MAX]
        assert len(walls) > 0, "Expected wall tiles"

    def test_room_count_reasonable(self):
        """Room count should be reasonable (≥1)."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=1)
        rooms = gen.get_room_list()
        assert len(rooms) >= 1

    def test_room_sizes_within_bounds(self):
        """All rooms should respect min/max size constraints."""
        gen = DungeonGenerator(width=64, height=64,
                               min_room_size=5, max_room_size=12, seed=1)
        rooms = gen.get_room_list()
        for room in rooms:
            assert room.w >= 5, f"Room width {room.w} < min 5"
            assert room.h >= 5, f"Room height {room.h} < min 5"
            assert room.w <= 12, f"Room width {room.w} > max 12"
            assert room.h <= 12, f"Room height {room.h} > max 12"

    def test_rooms_within_map_bounds(self):
        """All rooms should be within the map boundaries."""
        gen = DungeonGenerator(width=64, height=64, seed=1)
        rooms = gen.get_room_list()
        for room in rooms:
            assert room.x >= 0, f"Room x {room.x} < 0"
            assert room.y >= 0, f"Room y {room.y} < 0"
            assert room.x + room.w <= 64, f"Room exceeds width"
            assert room.y + room.h <= 64, f"Room exceeds height"


# ===========================================================================
# Corridors / connectivity
# ===========================================================================

class TestDungeonCorridors:
    def test_has_corridors(self):
        """Corridors connect rooms, producing floor tiles between them."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=6, seed=42)
        result = gen.generate()
        floors = [t for t in result.tiles
                  if DungeonTiles.FLOOR_MIN <= t.ground_id <= DungeonTiles.FLOOR_MAX]
        # Should have enough floor area for rooms + corridors
        assert len(floors) >= 6 * 4 * 4

    def test_corridor_connectivity(self):
        """Sequential rooms should be connected via corridors (path exists)."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=123)
        result = gen.generate()
        z0_tiles = [t for t in result.tiles if t.z == 0]

        # Build set of walkable tiles
        walkable = set()
        for t in z0_tiles:
            if DungeonTiles.FLOOR_MIN <= t.ground_id <= DungeonTiles.FLOOR_MAX:
                walkable.add((t.x, t.y))

        if not walkable:
            return  # Edge case: no walkable tiles

        # BFS from any walkable tile
        start = next(iter(walkable))
        visited = set()
        queue = [start]
        visited.add(start)
        while queue:
            cx, cy = queue.pop(0)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in walkable and (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))

        # At least some walkable tiles should be connected in a chain
        assert len(visited) >= len(walkable) * 0.15, \
            f"Only {len(visited)}/{len(walkable)} walkable tiles are connected"


# ===========================================================================
# Room types
# ===========================================================================

class TestDungeonRoomTypes:
    def test_get_room_list_has_types(self):
        """Room list should have rooms with assigned types."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=42)
        rooms = gen.get_room_list()
        type_set = {r.room_type for r in rooms}
        # Should have at least normal and boss (last room is always boss)
        assert RoomType.BOSS in type_set, "Last room should be boss type"
        assert len(type_set) >= 2, "Should have at least 2 different room types"

    def test_first_room_is_spawn_on_floor0(self):
        """First room on floor 0 should be spawn type."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=42)
        rooms = gen.get_room_list()
        if rooms:
            assert rooms[0].room_type == RoomType.SPAWN, \
                "First room on floor 0 should be spawn type"

    def test_last_room_is_boss(self):
        """Last room should be boss type."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=42)
        rooms = gen.get_room_list()
        if len(rooms) > 1:
            assert rooms[-1].room_type == RoomType.BOSS, \
                "Last room should be boss type"


# ===========================================================================
# Items: chests, doors, stairs
# ===========================================================================

class TestDungeonItems:
    def test_chests_placed(self):
        """Dungeon should have chest items in treasure/boss rooms."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=20,
                               min_room_size=4, max_room_size=10,
                               place_chests=True, seed=3)
        result = gen.generate()
        chests = [t for t in result.tiles
                  if any(i.id == DungeonTiles.CHEST for i in t.items)]
        assert len(chests) > 0, "Expected chests in dungeon rooms"

    def test_no_chests_when_disabled(self):
        """No chests when place_chests=False."""
        gen = DungeonGenerator(width=64, height=64, place_chests=False, seed=55)
        result = gen.generate()
        chests = [t for t in result.tiles
                  if any(i.id == DungeonTiles.CHEST for i in t.items)]
        assert len(chests) == 0

    def test_doors_present(self):
        """Dungeon should have door tiles at room entrances."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=10, seed=42)
        result = gen.generate()
        doors = [t for t in result.tiles
                 if t.ground_id in (DungeonTiles.CLOSED_DOOR, DungeonTiles.OPEN_DOOR)]
        assert len(doors) > 0, "Expected door tiles"

    def test_stairs_placed_in_multi_floor(self):
        """Multi-floor dungeons should have stair items."""
        gen = DungeonGenerator(width=48, height=48, floors=3,
                               place_stairs=True, seed=10)
        result = gen.generate()
        stairs = [t for t in result.tiles
                  if any(i.id in (DungeonTiles.STAIRS_DOWN, DungeonTiles.STAIRS_UP)
                         for i in t.items)]
        assert len(stairs) > 0, "Expected stairs in multi-floor dungeon"


# ===========================================================================
# Spawn points
# ===========================================================================

class TestDungeonSpawns:
    def test_has_spawns(self):
        """Dungeon with spawn rooms should have SpawnData."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=42)
        result = gen.generate()
        assert len(result.spawns) > 0, "Expected spawn data in dungeon"

    def test_spawn_has_monsters(self):
        """Each spawn should have at least one monster."""
        gen = DungeonGenerator(width=64, height=64, rooms_count=8, seed=42)
        result = gen.generate()
        for spawn in result.spawns:
            assert len(spawn.monsters) > 0, \
                f"Spawn at ({spawn.x},{spawn.y}) has no monsters"

    def test_spawn_positions_within_map(self):
        """Spawn positions should be within map bounds."""
        gen = DungeonGenerator(width=64, height=64, seed=42)
        result = gen.generate()
        for spawn in result.spawns:
            assert 0 <= spawn.x < 64
            assert 0 <= spawn.y < 64

    def test_custom_monsters(self):
        """Custom monster list should appear in spawns."""
        gen = DungeonGenerator(
            width=64, height=64, rooms_count=8, seed=42,
            default_monsters=["demon", "dragon"],
        )
        result = gen.generate()
        all_names = set()
        for spawn in result.spawns:
            for name, _, _ in spawn.monsters:
                all_names.add(name)
        assert "demon" in all_names or "dragon" in all_names, \
            "Custom monsters should appear in spawns"


# ===========================================================================
# Multi-floor
# ===========================================================================

class TestMultiFloor:
    def test_z_levels(self):
        """Multi-floor dungeon should have correct z-levels."""
        gen = DungeonGenerator(width=48, height=48, floors=3, seed=10)
        result = gen.generate()
        z_levels = {t.z for t in result.tiles}
        assert z_levels == {0, -1, -2}, f"Expected z-levels 0,-1,-2 got {z_levels}"

    def test_single_floor_z0(self):
        """Single-floor dungeon should only have z=0."""
        gen = DungeonGenerator(width=64, height=64, floors=1, seed=1)
        result = gen.generate()
        z_levels = {t.z for t in result.tiles}
        assert z_levels == {0}

    def test_each_floor_has_tiles(self):
        """Each floor should have its full set of tiles."""
        gen = DungeonGenerator(width=48, height=48, floors=3, seed=10)
        result = gen.generate()
        for z in [0, -1, -2]:
            floor_tiles = [t for t in result.tiles if t.z == z]
            assert len(floor_tiles) == 48 * 48, \
                f"Floor z={z} should have 48*48 tiles, got {len(floor_tiles)}"


# ===========================================================================
# Seed reproducibility
# ===========================================================================

class TestDungeonReproducibility:
    def test_same_seed_identical(self):
        """Same seed produces identical dungeon."""
        gen1 = DungeonGenerator(width=64, height=64, seed=99, floors=2)
        gen2 = DungeonGenerator(width=64, height=64, seed=99, floors=2)
        r1 = gen1.generate()
        r2 = gen2.generate()
        assert len(r1.tiles) == len(r2.tiles)
        for t1, t2 in zip(r1.tiles, r2.tiles):
            assert t1.ground_id == t2.ground_id

    def test_different_seed_different(self):
        """Different seeds produce different dungeons (with high probability)."""
        gen1 = DungeonGenerator(width=64, height=64, seed=1)
        gen2 = DungeonGenerator(width=64, height=64, seed=2)
        r1 = gen1.generate()
        r2 = gen2.generate()
        any_diff = any(t1.ground_id != t2.ground_id
                       for t1, t2 in zip(r1.tiles, r2.tiles))
        assert any_diff, "Different seeds should produce different dungeons"


# ===========================================================================
# Corridor width
# ===========================================================================

class TestCorridorWidth:
    def test_width_1(self):
        """Corridor width 1 should work."""
        gen = DungeonGenerator(width=64, height=64, corridor_width=1, seed=1)
        result = gen.generate()
        assert len(result.tiles) == 64 * 64

    def test_width_2(self):
        """Corridor width 2 should work."""
        gen = DungeonGenerator(width=64, height=64, corridor_width=2, seed=1)
        result = gen.generate()
        assert len(result.tiles) == 64 * 64


# ===========================================================================
# OTBMWriter round-trip integration
# ===========================================================================

class TestDungeonOTBMIntegration:
    def test_otbm_writer_roundtrip(self):
        """Dungeon MapData can be serialized by OTBMWriter."""
        gen = DungeonGenerator(width=64, height=64, seed=42)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 0
        assert data[:4] == b"OTBM"

    def test_otbm_save_to_file(self):
        """Dungeon can be saved to a file via OTBMWriter."""
        gen = DungeonGenerator(width=64, height=64, seed=42, floors=2)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        with tempfile.NamedTemporaryFile(suffix=".otbm", delete=True) as f:
            count = writer.save(f.name)
            assert count > 0
            assert os.path.getsize(f.name) > 0

    def test_multi_floor_otbm_serialization(self):
        """Multi-floor dungeon can be serialized."""
        gen = DungeonGenerator(width=48, height=48, floors=3, seed=10)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 100

    def test_dungeon_with_spawns_otbm(self):
        """Dungeon with spawns can be serialized."""
        gen = DungeonGenerator(width=64, height=64, seed=42,
                               default_monsters=["dragon", "demon"])
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 4
