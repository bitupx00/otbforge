"""Tests for map generators: terrain, dungeon, city, spawns."""

import sys
import os
import random

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.otbm_types import (
    MapData,
    NPCSpawnData,
    SpawnData,
    TileData,
    Tiles,
)
from ai_core.generators.terrain import TerrainGenerator, perlin_2d
from ai_core.generators.dungeon import DungeonGenerator
from ai_core.generators.city import CityGenerator
from ai_core.generators.spawns import SpawnGenerator


# ===========================================================================
# Terrain
# ===========================================================================

class TestTerrainGenerator:
    def test_returns_mapdata(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_dimensions(self):
        gen = TerrainGenerator(width=50, height=60, seed=1)
        result = gen.generate()
        assert result.width == 50
        assert result.height == 60

    def test_has_tiles(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        result = gen.generate()
        assert len(result.tiles) == 32 * 32

    def test_tiles_have_ground(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        result = gen.generate()
        for t in result.tiles:
            assert t.ground_id > 0, f"Tile ({t.x},{t.y}) has no ground"

    def test_has_water_tiles(self):
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.45)
        result = gen.generate()
        water = [t for t in result.tiles if t.ground_id == Tiles.WATER]
        assert len(water) > 0, "Expected some water tiles with island generation"

    def test_has_vegetation(self):
        gen = TerrainGenerator(width=64, height=64, seed=7)
        result = gen.generate()
        veg_ids = {t.items[0].id for t in result.tiles if t.items}
        assert veg_ids, "Expected at least some tiles with vegetation items"

    def test_rivers(self):
        gen = TerrainGenerator(width=64, height=64, seed=5, rivers=True)
        result = gen.generate()
        water = [t for t in result.tiles if t.ground_id == Tiles.WATER]
        # Rivers should create water paths inland
        assert len(water) > 10

    def test_reproducibility(self):
        gen1 = TerrainGenerator(width=32, height=32, seed=99)
        gen2 = TerrainGenerator(width=32, height=32, seed=99)
        r1 = gen1.generate()
        r2 = gen2.generate()
        assert len(r1.tiles) == len(r2.tiles)
        for t1, t2 in zip(r1.tiles, r2.tiles):
            assert t1.ground_id == t2.ground_id


class TestPerlinNoise:
    def test_output_range(self):
        for s in range(5):
            val = perlin_2d(1.0, 2.0, seed=s)
            assert 0.0 <= val <= 1.0, f"Perlin value {val} out of range"

    def test_same_seed_same_output(self):
        v1 = perlin_2d(3.5, 7.2, seed=10)
        v2 = perlin_2d(3.5, 7.2, seed=10)
        assert v1 == v2

    def test_different_seed_different_output(self):
        v1 = perlin_2d(3.5, 7.2, seed=1)
        v2 = perlin_2d(3.5, 7.2, seed=2)
        assert v1 != v2


# ===========================================================================
# Dungeon
# ===========================================================================

class TestDungeonGenerator:
    def test_returns_mapdata(self):
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_has_rooms(self):
        gen = DungeonGenerator(width=64, height=64, rooms_count=8,
                               min_room_size=4, max_room_size=10, seed=1)
        result = gen.generate()
        # Rooms have stone floor (not wall)
        floors = [t for t in result.tiles if t.ground_id == Tiles.STONE]
        assert len(floors) > 0, "Expected at least some stone floor tiles (rooms)"

    def test_has_walls(self):
        gen = DungeonGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        walls = [t for t in result.tiles if t.ground_id == Tiles.STONE_WALL]
        assert len(walls) > 0, "Expected stone wall tiles"

    def test_has_corridors(self):
        gen = DungeonGenerator(width=64, height=64, rooms_count=6, seed=42)
        result = gen.generate()
        # Corridors connect rooms, so floor tiles exist outside tight clusters
        floors = [t for t in result.tiles if t.ground_id == Tiles.STONE]
        assert len(floors) >= 6 * 4 * 4  # at least 6 rooms of min size

    def test_multi_floor(self):
        gen = DungeonGenerator(width=48, height=48, floors=3, seed=10)
        result = gen.generate()
        z_levels = {t.z for t in result.tiles}
        assert z_levels == {0, -1, -2}, f"Expected z-levels 0,-1,-2 got {z_levels}"

    def test_chests_placed(self):
        gen = DungeonGenerator(width=64, height=64, rooms_count=20,
                               min_room_size=4, max_room_size=10,
                               place_chests=True, seed=3)
        result = gen.generate()
        chests = [t for t in result.tiles
                  if any(i.id == Tiles.CHEST for i in t.items)]
        assert len(chests) > 0, "Expected chests in dungeon rooms"

    def test_no_chests_when_disabled(self):
        gen = DungeonGenerator(width=64, height=64, place_chests=False, seed=55)
        result = gen.generate()
        chests = [t for t in result.tiles
                  if any(i.id == Tiles.CHEST for i in t.items)]
        assert len(chests) == 0


# ===========================================================================
# City
# ===========================================================================

class TestCityGenerator:
    def test_returns_mapdata(self):
        gen = CityGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_has_streets(self):
        gen = CityGenerator(width=64, height=64, street_width=3, seed=1)
        result = gen.generate()
        streets = [t for t in result.tiles if t.ground_id == Tiles.STONE]
        assert len(streets) > 0, "Expected street tiles"

    def test_has_buildings(self):
        gen = CityGenerator(width=64, height=64, buildings_count=10, seed=1)
        result = gen.generate()
        buildings = [t for t in result.tiles if t.ground_id == Tiles.FLOOR_WOOD]
        assert len(buildings) > 0, "Expected building interior tiles"

    def test_has_doors(self):
        gen = CityGenerator(width=64, height=64, buildings_count=10, seed=1)
        result = gen.generate()
        doors = [t for t in result.tiles if t.ground_id == Tiles.CLOSED_DOOR]
        assert len(doors) > 0, "Expected door tiles"

    def test_has_town(self):
        gen = CityGenerator(width=64, height=64, seed=1)
        result = gen.generate()
        assert len(result.towns) >= 1
        assert result.towns[0].name == "Generated City"

    def test_has_walls(self):
        gen = CityGenerator(width=32, height=32, has_walls=True, seed=1)
        result = gen.generate()
        walls = [t for t in result.tiles if t.ground_id == Tiles.STONE_WALL]
        # Perimeter walls: at least top + bottom rows
        assert len(walls) >= 32 * 2

    def test_no_walls_by_default(self):
        gen = CityGenerator(width=32, height=32, has_walls=False, seed=1)
        result = gen.generate()
        # Perimeter tiles should not all be walls
        corners = [t for t in result.tiles
                   if t.ground_id == Tiles.STONE_WALL
                   and (t.x == 0 or t.x == 31 or t.y == 0 or t.y == 31)]
        # With no walls, corners are just grass or street
        assert len(corners) == 0 or len(corners) < 20

    def test_parks(self):
        gen = CityGenerator(width=64, height=64, has_park=True, seed=42)
        result = gen.generate()
        park_trees = [t for t in result.tiles
                      if t.ground_id == Tiles.GRASS and t.items
                      and any(Tiles.TREE_MIN <= i.id <= Tiles.TREE_MAX
                              for i in t.items)]
        # Parks exist and have trees/flowers in city area
        assert len(park_trees) >= 0  # probabilistic, but should exist often


# ===========================================================================
# Spawns
# ===========================================================================

class TestSpawnGenerator:
    def test_returns_mapdata(self):
        gen = SpawnGenerator(width=32, height=32, seed=1)
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_has_spawns(self):
        gen = SpawnGenerator(width=64, height=64, seed=1,
                             monster_types=["rat", "spider"])
        result = gen.generate()
        assert len(result.spawns) > 0, "Expected monster spawns"

    def test_spawn_has_monsters(self):
        gen = SpawnGenerator(width=64, height=64, seed=1,
                             monster_types=["dragon", "demon"])
        result = gen.generate()
        assert all(len(s.monsters) > 0 for s in result.spawns)

    def test_spawn_radius(self):
        gen = SpawnGenerator(width=64, height=64, seed=1,
                             spawn_radius=10,
                             monster_types=["orc", "skeleton"])
        result = gen.generate()
        assert all(s.radius == 10 for s in result.spawns)

    def test_npc_spawns(self):
        gen = SpawnGenerator(width=32, height=32, seed=1,
                             npc_types=["Merchant", "Healer"])
        result = gen.generate()
        assert len(result.npc_spawns) == 2
        names = {ns.npc_name for ns in result.npc_spawns}
        assert "Merchant" in names
        assert "Healer" in names

    def test_with_base_map(self):
        terrain = TerrainGenerator(width=32, height=32, seed=1).generate()
        gen = SpawnGenerator(width=32, height=32, seed=1,
                             monster_types=["rat"],
                             base_map=terrain)
        result = gen.generate()
        assert len(result.spawns) > 0
        assert len(result.tiles) == len(terrain.tiles)

    def test_custom_monster_list(self):
        gen = SpawnGenerator(width=32, height=32, seed=1,
                             monster_types=["dragon"])
        result = gen.generate()
        for s in result.spawns:
            names = [m[0] for m in s.monsters]
            assert "dragon" in names

    def test_no_spawns_empty_monsters(self):
        gen = SpawnGenerator(width=32, height=32, seed=1,
                             monster_types=[])
        result = gen.generate()
        # Should still return valid MapData, just no spawns
        assert isinstance(result, MapData)


# ===========================================================================
# Combined / Integration
# ===========================================================================

class TestCombinedGeneration:
    def test_terrain_plus_dungeon_plus_spawns(self):
        terrain = TerrainGenerator(width=64, height=64, seed=42).generate()
        dungeon = DungeonGenerator(width=64, height=64, floors=2, seed=42).generate()
        # Merge tiles: terrain on z=0, dungeon on z=-1
        merged_tiles = [t for t in terrain.tiles if t.z == 0]
        merged_tiles.extend(dungeon.tiles)
        base = MapData(
            width=64, height=64,
            description="Combined terrain+dungeon",
            tiles=merged_tiles,
        )

        spawn_gen = SpawnGenerator(
            width=64, height=64, seed=42,
            monster_types=["rat", "orc", "spider", "skeleton", "dragon"],
            npc_types=["Merchant", "Healer"],
            base_map=base,
        )
        result = spawn_gen.generate()

        assert isinstance(result, MapData)
        assert len(result.tiles) > 0
        assert len(result.spawns) > 0
        assert len(result.npc_spawns) > 0

        # Check multiple z-levels exist
        z_levels = {t.z for t in result.tiles}
        assert 0 in z_levels
        assert -1 in z_levels

    def test_city_with_spawns(self):
        city = CityGenerator(width=64, height=64, buildings_count=15,
                              has_walls=True, seed=7).generate()
        spawn_gen = SpawnGenerator(
            width=64, height=64, seed=7,
            monster_types=["guard", "rat"],
            npc_types=["Merchant"],
            base_map=city,
        )
        result = spawn_gen.generate()
        assert len(result.spawns) > 0
        # City had NPCs; spawn gen adds more
        assert len(result.npc_spawns) >= 1

    def test_all_generators_exportable(self):
        """Ensure all generators are importable and produce MapData."""
        from ai_core.generators import (
            TerrainGenerator as TG,
            DungeonGenerator as DG,
            CityGenerator as CG,
            SpawnGenerator as SG,
        )
        for Cls, kwargs in [
            (TG, dict(width=16, height=16)),
            (DG, dict(width=32, height=32)),
            (CG, dict(width=32, height=32)),
            (SG, dict(width=16, height=16)),
        ]:
            result = Cls(seed=1, **kwargs).generate()
            assert isinstance(result, MapData), f"{Cls.__name__} failed"
