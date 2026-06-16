"""Tests for water features generator: lakes, wells, oases, fountains."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.otbm_types import MapData, TileData, Tiles
from ai_core.generators.water_features import WaterFeatureGenerator, WaterTiles


# ===========================================================================
# Helpers
# ===========================================================================

def _make_plain_map(w=50, h=50, ground=Tiles.GRASS) -> MapData:
    tiles = [TileData(x=x, y=y, z=0, ground_id=ground) for x in range(w) for y in range(h)]
    return MapData(width=w, height=h, tiles=tiles, description="test")


def _make_sand_map(w=50, h=50) -> MapData:
    tiles = [TileData(x=x, y=y, z=0, ground_id=Tiles.SAND) for x in range(w) for y in range(h)]
    return MapData(width=w, height=h, tiles=tiles, description="sand")


# ===========================================================================
# Test: Lakes
# ===========================================================================

class TestLakes:
    def test_lake_has_water_tiles(self):
        """Lake should contain water tiles."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, num_lakes=1, seed=42)
        result = gen.place_lake(25, 25)

        water_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.WATER]
        assert len(water_tiles) > 0, "Lake should contain water tiles"

    def test_lake_has_shore(self):
        """Lake should have sand/shore tiles around the water."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, num_lakes=1, seed=42)
        result = gen.place_lake(25, 25)

        shore_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.SAND]
        assert len(shore_tiles) > 0, "Lake should have shore/sand tiles"

    def test_lake_elliptical_shape(self):
        """Lake water tiles should form an elliptical shape."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, num_lakes=1, seed=42,
                                     lake_size_range=(5, 5))
        result = gen.place_lake(25, 25)

        water_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.WATER]
        # All water tiles should be within expected radius of center
        for t in water_tiles:
            dist = ((t.x - 25) ** 2 + (t.y - 25) ** 2) ** 0.5
            assert dist <= 8, f"Water tile at {t.x},{t.y} too far from center (dist={dist})"

    def test_multiple_lakes(self):
        """Multiple lakes should each have water tiles."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, num_lakes=3, seed=42)
        result = gen.generate()

        water_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.WATER]
        assert len(water_tiles) > 10, "Multiple lakes should produce many water tiles"


# ===========================================================================
# Test: Wells
# ===========================================================================

class TestWells:
    def test_well_placed(self):
        """Well should be placed as an item on a tile."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.place_well(25, 25)

        well_tiles = [t for t in result.tiles
                      if any(item.id == WaterTiles.WELL_ITEM for item in t.items)]
        assert len(well_tiles) == 1, "Exactly one well should be placed"

    def test_well_location(self):
        """Well should be at the specified position."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.place_well(30, 20)

        tile_at_pos = [t for t in result.tiles if t.x == 30 and t.y == 20 and t.z == 0]
        assert len(tile_at_pos) == 1
        assert any(item.id == WaterTiles.WELL_ITEM for item in tile_at_pos[0].items)

    def test_well_in_generate(self):
        """Wells should be placed when calling generate()."""
        map_data = _make_plain_map(100, 100)
        gen = WaterFeatureGenerator(map_data=map_data, num_wells=2, seed=42)
        result = gen.generate()

        well_tiles = [t for t in result.tiles
                      if any(item.id == WaterTiles.WELL_ITEM for item in t.items)]
        assert len(well_tiles) >= 1, "At least one well should be placed"


# ===========================================================================
# Test: Oases
# ===========================================================================

class TestOases:
    def test_oasis_has_water(self):
        """Oasis should contain water tiles."""
        map_data = _make_sand_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.place_oasis(25, 25)

        water_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.WATER]
        assert len(water_tiles) > 0, "Oasis should have water"

    def test_oasis_has_palm_trees(self):
        """Oasis should have palm tree items around the water."""
        map_data = _make_sand_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.place_oasis(25, 25)

        palm_tiles = [t for t in result.tiles
                      if any(item.id == WaterTiles.PALM_TREE for item in t.items)]
        assert len(palm_tiles) > 0, "Oasis should have palm trees"

    def test_oasis_small(self):
        """Oasis should be small (radius ~4)."""
        map_data = _make_sand_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.place_oasis(25, 25)

        water_tiles = [t for t in result.tiles if t.ground_id == WaterTiles.WATER]
        for t in water_tiles:
            dist = ((t.x - 25) ** 2 + (t.y - 25) ** 2) ** 0.5
            assert dist <= 3, f"Oasis water tile at {t.x},{t.y} too far from center"


# ===========================================================================
# Test: Fountains
# ===========================================================================

class TestFountains:
    def test_fountain_placed(self):
        """Fountain should be placed as an item on a tile."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, num_fountains=1, seed=42)
        result = gen.generate()

        fountain_tiles = [t for t in result.tiles
                          if any(item.id == WaterTiles.FOUNTAIN_ITEM for item in t.items)]
        assert len(fountain_tiles) >= 1, "At least one fountain should be placed"

    def test_fountain_on_paved_ground(self):
        """Fountain tile should have cobblestone ground."""
        map_data = _make_plain_map()
        gen = WaterFeatureGenerator(map_data=map_data, seed=42)
        result = gen.generate()

        fountain_tiles = [t for t in result.tiles
                          if any(item.id == WaterTiles.FOUNTAIN_ITEM for item in t.items)]
        for ft in fountain_tiles:
            assert ft.ground_id == 355, f"Fountain at {ft.x},{ft.y} should have cobblestone ground"
