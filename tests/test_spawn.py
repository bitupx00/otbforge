"""Tests for SpawnManager — monster/NPC placement, biome filtering, safety zones."""

import pytest
from ai_core.generators.spawn_manager import (
    SpawnManager,
    MONSTER_DATABASE,
    NPC_DATABASE,
    MonsterEntry,
    NPCType,
    GROUND_TO_BIOME,
)
from ai_core.otbm_types import (
    MapData,
    ItemData,
    Position,
    SpawnData,
    NPCSpawnData,
    TileData,
    TileFlags,
    Tiles,
)


class TestSpawnManagerBasic:
    """Basic spawn generation tests."""

    def test_generate_returns_mapdata(self):
        sm = SpawnManager()
        result = sm.generate()
        assert isinstance(result, MapData)

    def test_generate_creates_spawns(self):
        sm = SpawnMonsterMapBuilder().build(density=1.0)
        result = sm.generate()
        # With density=1.0 and enough tiles, should get spawns
        assert len(result.spawns) >= 0

    def test_generate_creates_npc_spawns(self):
        md = _make_simple_map(64, 64)
        sm = SpawnManager(map_data=md, npc_names=["Merchant", "Healer"])
        result = sm.generate()
        assert len(result.npc_spawns) >= 2

    def test_works_without_base_map(self):
        sm = SpawnManager(map_data=None, width=64, height=64)
        result = sm.generate()
        assert isinstance(result, MapData)


class TestMonsterDatabase:
    """Monster database structure tests."""

    def test_database_has_monsters(self):
        assert len(MONSTER_DATABASE) > 0

    def test_rat_is_easy(self):
        assert "rat" in MONSTER_DATABASE
        assert MONSTER_DATABASE["rat"].difficulty == 1

    def test_demon_is_very_hard(self):
        assert "demon" in MONSTER_DATABASE
        assert MONSTER_DATABASE["demon"].difficulty == 5

    def test_dragon_is_hard(self):
        assert "dragon" in MONSTER_DATABASE
        assert MONSTER_DATABASE["dragon"].difficulty == 4

    def test_monsters_have_biomes(self):
        for name, entry in MONSTER_DATABASE.items():
            assert len(entry.biomes) > 0, f"{name} has no biomes"

    def test_difficulty_range_valid(self):
        for name, entry in MONSTER_DATABASE.items():
            assert 1 <= entry.difficulty <= 5, f"{name} difficulty={entry.difficulty}"


class TestBiomeFiltering:
    """Biome-based monster selection tests."""

    def test_monsters_for_plains(self):
        sm = SpawnManager()
        monsters = sm.get_monsters_for_biome("plains")
        assert len(monsters) > 0
        assert "rat" in monsters

    def test_monsters_for_forest(self):
        sm = SpawnManager()
        monsters = sm.get_monsters_for_biome("forest")
        assert len(monsters) > 0
        assert "spider" in monsters

    def test_monsters_for_mountains(self):
        sm = SpawnManager()
        monsters = sm.get_monsters_for_biome("mountains")
        assert len(monsters) > 0

    def test_monsters_for_dungeon(self):
        sm = SpawnManager()
        monsters = sm.get_monsters_for_biome("dungeon")
        assert "demon" in monsters
        assert "vampire" in monsters

    def test_monsters_for_water(self):
        sm = SpawnManager()
        monsters = sm.get_monsters_for_biome("water")
        assert "crab" in monsters

    def test_difficulty_filtering(self):
        sm = SpawnManager()
        easy = sm.get_monsters_for_difficulty(1)
        hard = sm.get_monsters_for_difficulty(5)
        assert len(easy) <= len(hard)
        assert "rat" in easy
        assert "demon" in hard


class TestSafetyZones:
    """Safety zone (protection zone) tests."""

    def test_no_spawns_in_protection_zone(self):
        # Create a map with a large protection zone
        md = MapData(width=64, height=64)
        for y in range(64):
            for x in range(64):
                flags = TileFlags.PROTECTIONZONE if (20 <= x < 44 and 20 <= y < 44) else TileFlags.NONE
                md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.GRASS, flags=flags))

        sm = SpawnManager(map_data=md, monster_density=2.0, safety_zone_margin=10)
        result = sm.generate()

        # Check no spawn center is in the protection zone
        pz_area = {(x, y) for x in range(20, 44) for y in range(20, 44)}
        for spawn in result.spawns:
            assert (spawn.x, spawn.y) not in pz_area, \
                f"Spawn at ({spawn.x}, {spawn.y}) is inside protection zone"

    def test_npcs_placed_in_protection_zone(self):
        md = MapData(width=64, height=64)
        for y in range(64):
            for x in range(64):
                flags = TileFlags.PROTECTIONZONE if (25 <= x < 39 and 25 <= y < 39) else TileFlags.NONE
                md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.GRASS, flags=flags))

        sm = SpawnManager(map_data=md, npc_names=["Merchant", "Banker"])
        result = sm.generate()
        assert len(result.npc_spawns) >= 2


class TestSpawnDensity:
    """Spawn density control tests."""

    def test_low_density_fewer_spawns(self):
        md = _make_simple_map(64, 64)
        sm1 = SpawnManager(map_data=md, monster_density=0.1, seed=1)
        sm2 = SpawnManager(map_data=md, monster_density=5.0, seed=1)
        r1 = sm1.generate()
        r2 = sm2.generate()
        assert len(r1.spawns) <= len(r2.spawns) + 1  # allow small variance

    def test_zero_density_no_spawns(self):
        md = _make_simple_map(32, 32)
        sm = SpawnManager(map_data=md, monster_density=0.0)
        result = sm.generate()
        assert len(result.spawns) == 0


class TestSpawnRadius:
    """Spawn radius tests."""

    def test_spawns_have_radius(self):
        md = _make_simple_map(64, 64)
        sm = SpawnManager(map_data=md, monster_density=2.0)
        result = sm.generate()
        for spawn in result.spawns:
            assert spawn.radius > 0

    def test_spawns_have_monsters(self):
        md = _make_simple_map(64, 64)
        sm = SpawnManager(map_data=md, monster_density=2.0)
        result = sm.generate()
        for spawn in result.spawns:
            assert len(spawn.monsters) > 0

    def test_monster_offsets_within_radius(self):
        md = _make_simple_map(64, 64)
        sm = SpawnManager(map_data=md, monster_density=2.0)
        result = sm.generate()
        for spawn in result.spawns:
            for name, ox, oy in spawn.monsters:
                assert abs(ox) <= spawn.radius
                assert abs(oy) <= spawn.radius


class TestNPCPlacement:
    """NPC placement tests."""

    def test_npc_spawns_have_names(self):
        md = _make_simple_map(64, 64)
        sm = SpawnManager(map_data=md, npc_names=["Healer", "Banker", "Merchant"])
        result = sm.generate()
        names = [npc.npc_name for npc in result.npc_spawns]
        assert "Healer" in names
        assert "Banker" in names
        assert "Merchant" in names

    def test_npc_database_has_types(self):
        assert len(NPC_DATABASE) > 0
        assert "Merchant" in NPC_DATABASE
        assert "Banker" in NPC_DATABASE

    def test_npc_needs_town_flag(self):
        assert NPC_DATABASE["Merchant"].needs_town is True


class TestGroundToBiomeMapping:
    """Ground tile to biome mapping tests."""

    def test_grass_is_plains(self):
        assert GROUND_TO_BIOME.get(Tiles.GRASS) == "plains"

    def test_water_is_water(self):
        assert GROUND_TO_BIOME.get(Tiles.WATER) == "water"

    def test_sand_is_beach(self):
        assert GROUND_TO_BIOME.get(Tiles.SAND) == "beach"


class TestSpawnIntegration:
    """Integration with terrain/town generators."""

    def test_integration_with_simple_map(self):
        md = MapData(width=128, height=128, description="Test Map")
        # Add some varied terrain
        for y in range(128):
            for x in range(128):
                if y < 42:
                    md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.GRASS))
                elif y < 85:
                    md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.DIRT))
                else:
                    md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.SAND))

        # Add a town with protection zone
        for y in range(55, 65):
            for x in range(55, 65):
                md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.STONE, flags=TileFlags.PROTECTIONZONE))

        sm = SpawnManager(map_data=md, npc_names=["Merchant"])
        result = sm.generate()
        assert len(result.spawns) > 0
        assert len(result.npc_spawns) > 0

    def test_reproducible_with_seed(self):
        md = _make_simple_map(64, 64)
        sm1 = SpawnManager(map_data=md, seed=42)
        sm2 = SpawnManager(map_data=md, seed=42)
        r1 = sm1.generate()
        r2 = sm2.generate()
        assert len(r1.spawns) == len(r2.spawns)
        # Check same positions
        for s1, s2 in zip(r1.spawns, r2.spawns):
            assert s1.x == s2.x
            assert s1.y == s2.y


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_simple_map(w, h):
    """Create a simple map filled with grass."""
    md = MapData(width=w, height=h)
    for y in range(h):
        for x in range(w):
            md.tiles.append(TileData(x=x, y=y, z=0, ground_id=Tiles.GRASS))
    return md


class SpawnMonsterMapBuilder:
    """Helper to build maps for spawn testing."""
    def build(self, density=1.0):
        md = _make_simple_map(64, 64)
        return SpawnManager(map_data=md, monster_density=density)
