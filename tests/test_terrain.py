"""Tests for terrain generator: Perlin noise, biomes, island shape, rivers,
vegetation, seed reproducibility, and OTBMWriter round-trip integration."""

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
from ai_core.generators.terrain import (
    Biome,
    BIOME_GROUND,
    TerrainGenerator,
    TerrainTiles,
    classify_biome,
    perlin_2d,
)


# ===========================================================================
# Perlin noise
# ===========================================================================

class TestPerlinNoise:
    def test_output_range(self):
        """Perlin output must be in [0, 1]."""
        for s in range(10):
            val = perlin_2d(1.0, 2.0, seed=s)
            assert 0.0 <= val <= 1.0, f"Perlin value {val} out of range for seed {s}"

    def test_same_seed_same_output(self):
        """Identical seeds produce identical values."""
        v1 = perlin_2d(3.5, 7.2, seed=10)
        v2 = perlin_2d(3.5, 7.2, seed=10)
        assert v1 == v2

    def test_different_seed_different_output(self):
        """Different seeds produce different values (with high probability)."""
        v1 = perlin_2d(3.5, 7.2, seed=1)
        v2 = perlin_2d(3.5, 7.2, seed=2)
        assert v1 != v2

    def test_different_position_different_output(self):
        """Different coordinates produce different values."""
        v1 = perlin_2d(0.0, 0.0, seed=42)
        v2 = perlin_2d(1.0, 1.0, seed=42)
        assert v1 != v2

    def test_two_octaves(self):
        """Perlin noise works with 2 octaves."""
        val = perlin_2d(5.0, 5.0, seed=1, octaves=2)
        assert 0.0 <= val <= 1.0

    def test_many_octaves(self):
        """Perlin noise works with 6 octaves."""
        val = perlin_2d(5.0, 5.0, seed=1, octaves=6)
        assert 0.0 <= val <= 1.0

    def test_custom_persistence(self):
        """Custom persistence parameter works."""
        v1 = perlin_2d(5.0, 5.0, seed=1, octaves=4, persistence=0.3)
        v2 = perlin_2d(5.0, 5.0, seed=1, octaves=4, persistence=0.8)
        assert v1 != v2


# ===========================================================================
# Biome classification
# ===========================================================================

class TestBiomeClassification:
    def test_deep_water(self):
        assert classify_biome(0.1, 0.5, 0.38) == Biome.DEEP_WATER

    def test_shallow_water(self):
        assert classify_biome(0.35, 0.5, 0.38) == Biome.SHALLOW_WATER

    def test_beach(self):
        assert classify_biome(0.39, 0.5, 0.38) == Biome.BEACH

    def test_snow_peaks(self):
        assert classify_biome(0.80, 0.5, 0.38) == Biome.SNOW_PEAKS

    def test_mountains(self):
        assert classify_biome(0.70, 0.5, 0.38) == Biome.MOUNTAINS

    def test_hills(self):
        assert classify_biome(0.58, 0.5, 0.38) == Biome.HILLS

    def test_plains(self):
        assert classify_biome(0.50, 0.35, 0.38) == Biome.PLAINS

    def test_forest(self):
        assert classify_biome(0.50, 0.45, 0.38) == Biome.FOREST

    def test_dense_forest(self):
        assert classify_biome(0.50, 0.65, 0.38) == Biome.DENSE_FOREST

    def test_swamp(self):
        """Low elevation + high moisture → swamp."""
        assert classify_biome(0.42, 0.70, 0.38) == Biome.SWAMP

    def test_jungle(self):
        """High moisture + moderate elevation → jungle."""
        assert classify_biome(0.50, 0.85, 0.38) == Biome.JUNGLE

    def test_all_biomes_have_ground_id(self):
        """Every biome constant maps to a valid ground tile ID."""
        for biome_name in [
            Biome.DEEP_WATER, Biome.SHALLOW_WATER, Biome.BEACH,
            Biome.PLAINS, Biome.FOREST, Biome.DENSE_FOREST,
            Biome.HILLS, Biome.MOUNTAINS, Biome.SNOW_PEAKS,
            Biome.SWAMP, Biome.JUNGLE,
        ]:
            assert biome_name in BIOME_GROUND, f"Missing ground for {biome_name}"
            assert BIOME_GROUND[biome_name] > 0


# ===========================================================================
# TerrainGenerator basic
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

    def test_tiles_on_z0(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        result = gen.generate()
        for t in result.tiles:
            assert t.z == 0


# ===========================================================================
# Island shape
# ===========================================================================

class TestIslandShape:
    def test_has_water_border(self):
        """Island generation should produce water at edges."""
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.35)
        result = gen.generate()
        # Corners should be water due to island falloff
        water_grounds = {TerrainTiles.WATER, TerrainTiles.SHALLOW_WATER}
        corners = [t for t in result.tiles
                   if (t.x == 0 or t.x == 63) and (t.y == 0 or t.y == 63)]
        water_corners = [t for t in corners if t.ground_id in water_grounds]
        assert len(water_corners) >= 2, "Expected water at some corners (island shape)"

    def test_has_land_in_center(self):
        """Center of island should have non-water tiles."""
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.25)
        result = gen.generate()
        center_tiles = [t for t in result.tiles
                        if 28 <= t.x <= 35 and 28 <= t.y <= 35]
        non_water = [t for t in center_tiles
                     if t.ground_id not in (TerrainTiles.WATER,)]
        assert len(non_water) > 0, "Expected land tiles at island center"


# ===========================================================================
# Biomes in generated map
# ===========================================================================

class TestBiomeTiles:
    def test_has_water_tiles(self):
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.45)
        result = gen.generate()
        water = [t for t in result.tiles if t.ground_id == TerrainTiles.WATER]
        assert len(water) > 0, "Expected water tiles"

    def test_has_sand_tiles(self):
        """Beach biome should produce sand tiles."""
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.30)
        result = gen.generate()
        sand = [t for t in result.tiles if t.ground_id == TerrainTiles.SAND]
        assert len(sand) > 0, "Expected sand (beach) tiles"

    def test_has_grass_tiles(self):
        gen = TerrainGenerator(width=64, height=64, seed=42, water_level=0.25)
        result = gen.generate()
        grass = [t for t in result.tiles if t.ground_id == TerrainTiles.GRASS]
        assert len(grass) > 0, "Expected grass tiles"

    def test_has_mountain_tiles(self):
        """Mountain tiles should appear on maps with low water level."""
        gen = TerrainGenerator(width=128, height=128, seed=2, water_level=0.10)
        result = gen.generate()
        mountains = [t for t in result.tiles
                     if t.ground_id == TerrainTiles.MOUNTAIN]
        assert len(mountains) > 0, "Expected mountain tiles"

    def test_has_snow_tiles(self):
        """Snow tiles should appear at highest elevations on maps with low water level."""
        gen = TerrainGenerator(width=128, height=128, seed=2, water_level=0.10)
        result = gen.generate()
        snow = [t for t in result.tiles if t.ground_id == TerrainTiles.SNOW]
        assert len(snow) > 0, "Expected snow tiles on map with low water level"

    def test_has_vegetation(self):
        """Map should have tiles with tree/flower/bush items."""
        gen = TerrainGenerator(width=64, height=64, seed=7, water_level=0.25)
        result = gen.generate()
        veg_tiles = [t for t in result.tiles if t.items]
        assert len(veg_tiles) > 0, "Expected tiles with vegetation items"

    def test_vegetation_ids_valid(self):
        """All vegetation item IDs should be in valid range."""
        gen = TerrainGenerator(width=64, height=64, seed=7, water_level=0.25)
        result = gen.generate()
        for t in result.tiles:
            for item in t.items:
                assert item.id > 0, f"Invalid item ID {item.id}"
                valid_ranges = [
                    (TerrainTiles.TREE_MIN, TerrainTiles.TREE_MAX),
                    (TerrainTiles.BUSH_1, TerrainTiles.BUSH_2),
                    (TerrainTiles.FLOWER_MIN, TerrainTiles.FLOWER_MAX),
                    (TerrainTiles.GRASS, TerrainTiles.GRASS),  # sparse grass on hills
                ]
                assert any(lo <= item.id <= hi for lo, hi in valid_ranges), \
                    f"Item ID {item.id} not in valid vegetation range"


# ===========================================================================
# Rivers
# ===========================================================================

class TestRivers:
    def test_river_tiles_present(self):
        """Rivers enabled should produce river tiles."""
        gen = TerrainGenerator(width=64, height=64, seed=5, rivers=True)
        result = gen.generate()
        rivers = [t for t in result.tiles if t.ground_id == TerrainTiles.RIVER]
        assert len(rivers) > 0, "Expected river tiles when rivers=True"

    def test_no_rivers_by_default(self):
        """Rivers disabled should not produce river tiles."""
        gen = TerrainGenerator(width=64, height=64, seed=5, rivers=False)
        result = gen.generate()
        rivers = [t for t in result.tiles if t.ground_id == TerrainTiles.RIVER]
        assert len(rivers) == 0, "Expected no river tiles when rivers=False"

    def test_rivers_create_water_paths(self):
        """Rivers should carve paths across the map."""
        gen = TerrainGenerator(width=64, height=64, seed=42, rivers=True,
                               num_rivers=2)
        result = gen.generate()
        rivers = [t for t in result.tiles if t.ground_id == TerrainTiles.RIVER]
        if rivers:
            # River tiles should span multiple rows/columns
            xs = {t.x for t in rivers}
            ys = {t.y for t in rivers}
            assert len(xs) > 1 or len(ys) > 1, "River should span multiple coordinates"


# ===========================================================================
# Seed reproducibility
# ===========================================================================

class TestSeedReproducibility:
    def test_same_seed_identical_output(self):
        """Two generators with same seed produce identical maps."""
        gen1 = TerrainGenerator(width=32, height=32, seed=99)
        gen2 = TerrainGenerator(width=32, height=32, seed=99)
        r1 = gen1.generate()
        r2 = gen2.generate()
        assert len(r1.tiles) == len(r2.tiles)
        for t1, t2 in zip(r1.tiles, r2.tiles):
            assert t1.ground_id == t2.ground_id
            assert len(t1.items) == len(t2.items)

    def test_different_seed_different_output(self):
        """Different seeds produce different maps (with high probability)."""
        gen1 = TerrainGenerator(width=32, height=32, seed=1)
        gen2 = TerrainGenerator(width=32, height=32, seed=2)
        r1 = gen1.generate()
        r2 = gen2.generate()
        # At least one tile should differ
        any_diff = any(t1.ground_id != t2.ground_id
                       for t1, t2 in zip(r1.tiles, r2.tiles))
        assert any_diff, "Different seeds should produce different maps"


# ===========================================================================
# Biome map / elevation map helpers
# ===========================================================================

class TestHelperMethods:
    def test_get_biome_map_dimensions(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        biome_map = gen.get_biome_map()
        assert len(biome_map) == 32
        assert len(biome_map[0]) == 32

    def test_get_biome_map_all_valid(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        biome_map = gen.get_biome_map()
        valid_biomes = {
            Biome.DEEP_WATER, Biome.SHALLOW_WATER, Biome.BEACH,
            Biome.PLAINS, Biome.FOREST, Biome.DENSE_FOREST,
            Biome.HILLS, Biome.MOUNTAINS, Biome.SNOW_PEAKS,
            Biome.SWAMP, Biome.JUNGLE,
        }
        for row in biome_map:
            for b in row:
                assert b in valid_biomes, f"Invalid biome: {b}"

    def test_get_elevation_map_dimensions(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        elev = gen.get_elevation_map()
        assert len(elev) == 32
        assert len(elev[0]) == 32

    def test_get_elevation_map_range(self):
        gen = TerrainGenerator(width=32, height=32, seed=1)
        elev = gen.get_elevation_map()
        for row in elev:
            for v in row:
                assert 0.0 <= v <= 1.0, f"Elevation {v} out of range"


# ===========================================================================
# OTBMWriter round-trip integration
# ===========================================================================

class TestTerrainOTBMIntegration:
    def test_otbm_writer_roundtrip(self):
        """Generated terrain can be serialized by OTBMWriter."""
        gen = TerrainGenerator(width=32, height=32, seed=42)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 0
        assert data[:4] == b"OTBM"

    def test_otbm_save_to_file(self):
        """Generated terrain can be saved to a file via OTBMWriter."""
        gen = TerrainGenerator(width=32, height=32, seed=42)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        with tempfile.NamedTemporaryFile(suffix=".otbm", delete=True) as f:
            count = writer.save(f.name)
            assert count > 0
            assert os.path.getsize(f.name) > 0

    def test_otbm_writer_with_rivers(self):
        """Terrain with rivers can be serialized."""
        gen = TerrainGenerator(width=32, height=32, seed=42, rivers=True)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 4

    def test_large_map_serialization(self):
        """Larger terrain (128x128) can be serialized."""
        gen = TerrainGenerator(width=128, height=128, seed=1)
        map_data = gen.generate()
        writer = OTBMWriter(map_data)
        data = writer.write()
        assert len(data) > 100
