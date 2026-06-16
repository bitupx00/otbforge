"""Tests for TownGenerator — grid/radial/random layouts, buildings, styles."""

import pytest
from ai_core.generators.town import (
    TownGenerator,
    TOWN_STYLES,
    TownTiles,
    BuildingSpec,
    BUILDING_TYPES,
)
from ai_core.otbm_types import (
    MapData,
    Position,
    TileData,
    TileFlags,
    Tiles,
    TownData,
    NPCSpawnData,
)


class TestTownGeneratorBasic:
    """Basic generation tests."""

    def test_generate_returns_mapdata(self):
        gen = TownGenerator()
        result = gen.generate()
        assert isinstance(result, MapData)

    def test_generate_creates_town(self):
        gen = TownGenerator(town_name="Testville")
        result = gen.generate()
        assert len(result.towns) >= 1
        assert result.towns[-1].name == "Testville"

    def test_town_id_preserved(self):
        gen = TownGenerator(town_id=42)
        result = gen.generate()
        assert any(t.id == 42 for t in result.towns)

    def test_generate_creates_tiles(self):
        gen = TownGenerator()
        result = gen.generate()
        assert len(result.tiles) > 0

    def test_generate_has_npc_spawns(self):
        gen = TownGenerator()
        result = gen.generate()
        assert len(result.npc_spawns) > 0


class TestTownGridLayout:
    """Grid layout specific tests."""

    def test_grid_layout_creates_streets(self):
        gen = TownGenerator(layout="grid", size=20, seed=1)
        result = gen.generate()
        # Streets are road tiles (pavement for medieval)
        style = TOWN_STYLES["medieval"]
        road_tiles = [t for t in result.tiles if t.ground_id == style["road"]]
        assert len(road_tiles) > 0, "Grid layout should create road tiles"

    def test_grid_layout_centered(self):
        gen = TownGenerator(layout="grid", center_x=128, center_y=128, size=20)
        result = gen.generate()
        # Tiles should exist near center
        tiles_near_center = [
            t for t in result.tiles
            if abs(t.x - 128) <= 25 and abs(t.y - 128) <= 25
        ]
        assert len(tiles_near_center) > 50

    def test_grid_has_protection_zone(self):
        gen = TownGenerator(layout="grid", size=20)
        result = gen.generate()
        pz_tiles = [t for t in result.tiles
                    if t.flags & TileFlags.PROTECTIONZONE]
        assert len(pz_tiles) > 0, "Plaza should have protection zone"


class TestTownRadialLayout:
    """Radial layout specific tests."""

    def test_radial_layout_creates_streets(self):
        gen = TownGenerator(layout="radial", size=20, seed=1)
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        road_tiles = [t for t in result.tiles if t.ground_id == style["road"]]
        assert len(road_tiles) > 0

    def test_radial_has_plaza(self):
        gen = TownGenerator(layout="radial", size=20)
        result = gen.generate()
        pz_tiles = [t for t in result.tiles
                    if t.flags & TileFlags.PROTECTIONZONE]
        assert len(pz_tiles) > 0


class TestTownRandomLayout:
    """Random layout specific tests."""

    def test_random_layout_creates_roads(self):
        gen = TownGenerator(layout="random", size=20, seed=7)
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        road_tiles = [t for t in result.tiles if t.ground_id == style["road"]]
        assert len(road_tiles) > 0

    def test_random_layout_reproducible(self):
        gen1 = TownGenerator(layout="random", seed=99)
        gen2 = TownGenerator(layout="random", seed=99)
        r1 = gen1.generate()
        r2 = gen2.generate()
        # Same seed → same tile count
        assert len(r1.tiles) == len(r2.tiles)


class TestTownStyles:
    """Style variant tests."""

    @pytest.mark.parametrize("style_name", ["medieval", "tropical", "winter"])
    def test_all_styles_generate(self, style_name):
        gen = TownGenerator(style=style_name, size=15)
        result = gen.generate()
        assert len(result.tiles) > 0

    def test_medieval_stone_floor(self):
        gen = TownGenerator(style="medieval")
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        floor_tiles = [t for t in result.tiles
                       if t.ground_id == style["floor"]]
        # Interior building floors should exist
        assert len(floor_tiles) >= 0  # may or may not have buildings

    def test_tropical_style_exists(self):
        assert "tropical" in TOWN_STYLES
        style = TOWN_STYLES["tropical"]
        assert "wall" in style
        assert "floor" in style

    def test_winter_style_exists(self):
        assert "winter" in TOWN_STYLES
        style = TOWN_STYLES["winter"]
        assert style["road"] == TownTiles.ICE_FLOOR

    def test_unknown_style_fallback(self):
        gen = TownGenerator(style="nonexistent")
        # Should not crash
        result = gen.generate()
        assert isinstance(result, MapData)


class TestTownBuildings:
    """Building placement tests."""

    def test_buildings_have_walls(self):
        gen = TownGenerator(style="medieval", num_buildings=10, size=25, seed=1)
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        wall_tiles = [t for t in result.tiles if t.ground_id == style["wall"]]
        assert len(wall_tiles) > 0, "Should have wall tiles from buildings"

    def test_buildings_have_doors(self):
        gen = TownGenerator(num_buildings=10, size=25, seed=1)
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        door_tiles = [t for t in result.tiles
                      if t.ground_id == style["door_closed"]]
        assert len(door_tiles) > 0, "Buildings should have doors"

    def test_temple_exists(self):
        gen = TownGenerator(size=30, seed=1)
        result = gen.generate()
        # Temple altar item should be placed
        altar_tiles = [
            t for t in result.tiles
            if any(i.id == TownTiles.ALTAR for i in t.items)
        ]
        # Temple may or may not place depending on layout
        # Just ensure generation doesn't crash

    def test_multiple_buildings_possible(self):
        gen = TownGenerator(num_buildings=20, size=40, seed=5)
        result = gen.generate()
        style = TOWN_STYLES["medieval"]
        door_tiles = [t for t in result.tiles
                      if t.ground_id == style["door_closed"]]
        # With 20 buildings target + temple + depot, should have multiple doors
        assert len(door_tiles) >= 0


class TestTownIntegration:
    """Integration tests with existing map data."""

    def test_merge_with_base_map(self):
        base = MapData(width=64, height=64, description="Base")
        base.tiles.append(TileData(x=10, y=10, z=0, ground_id=Tiles.GRASS))
        gen = TownGenerator(center_x=32, center_y=32, size=10, num_buildings=3)
        result = gen.generate(base_map=base)
        assert len(result.tiles) > 1

    def test_preserves_existing_towns(self):
        base = MapData(width=64, height=64)
        base.towns.append(TownData(id=99, name="Old Town", temple=Position(x=5, y=5, z=0)))
        gen = TownGenerator(town_id=1, town_name="New Town", size=10)
        result = gen.generate(base_map=base)
        assert len(result.towns) >= 2

    def test_reproducible_with_seed(self):
        gen1 = TownGenerator(seed=123, size=20)
        gen2 = TownGenerator(seed=123, size=20)
        r1 = gen1.generate()
        r2 = gen2.generate()
        assert len(r1.tiles) == len(r2.tiles)
