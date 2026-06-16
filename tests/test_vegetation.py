"""Tests for vegetation enhancer: tree clusters, flower patches, hedge rows, grass variation."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.otbm_types import MapData, TileData, Tiles
from ai_core.generators.vegetation import VegetationEnhancer, VegTiles


# ===========================================================================
# Helpers
# ===========================================================================

def _make_plain_map(w=50, h=50, ground=Tiles.GRASS) -> MapData:
    tiles = [TileData(x=x, y=y, z=0, ground_id=ground) for x in range(w) for y in range(h)]
    return MapData(width=w, height=h, tiles=tiles, description="test")


# ===========================================================================
# Test: Tree clusters
# ===========================================================================

class TestTreeClusters:
    def test_cluster_produces_trees(self):
        """Tree cluster should produce tree items."""
        map_data = _make_plain_map()
        gen = VegetationEnhancer(map_data=map_data, num_tree_clusters=1, seed=42)
        result = gen.place_tree_cluster(25, 25)

        tree_tiles = [t for t in result.tiles
                      if any(VegTiles.TREE_MIN <= item.id <= VegTiles.TREE_MAX for item in t.items)]
        assert len(tree_tiles) > 0, "Tree cluster should produce tree items"

    def test_cluster_centered(self):
        """Trees should be concentrated around the cluster center."""
        map_data = _make_plain_map(60, 60)
        gen = VegetationEnhancer(map_data=map_data, num_tree_clusters=1, seed=42, tree_density=0.5)
        result = gen.place_tree_cluster(30, 30)

        tree_tiles = [t for t in result.tiles
                      if any(VegTiles.TREE_MIN <= item.id <= VegTiles.TREE_MAX for item in t.items)]
        # Most trees should be within cluster_radius of center
        far_trees = [t for t in tree_tiles
                    if ((t.x - 30) ** 2 + (t.y - 30) ** 2) ** 0.5 > gen.cluster_radius]
        assert len(far_trees) == 0, f"No trees should be beyond cluster radius"

    def test_custom_cluster_radius(self):
        """Custom radius should be respected."""
        map_data = _make_plain_map(60, 60)
        gen = VegetationEnhancer(map_data=map_data, seed=42, cluster_radius=5)
        result = gen.place_tree_cluster(30, 30, radius=5)

        tree_tiles = [t for t in result.tiles
                      if any(VegTiles.TREE_MIN <= item.id <= VegTiles.TREE_MAX for item in t.items)]
        for t in tree_tiles:
            dist = ((t.x - 30) ** 2 + (t.y - 30) ** 2) ** 0.5
            assert dist <= 5, f"Tree at {t.x},{t.y} beyond custom radius 5"


# ===========================================================================
# Test: Flower patches
# ===========================================================================

class TestFlowerPatches:
    def test_enhance_produces_flowers(self):
        """Full enhance should produce flower items."""
        map_data = _make_plain_map()
        gen = VegetationEnhancer(map_data=map_data, flower_density=0.3, num_tree_clusters=0,
                                  num_hedge_rows=0, seed=42)
        result = gen.enhance()

        flower_tiles = [t for t in result.tiles
                        if any(VegTiles.FLOWER_MIN <= item.id <= VegTiles.FLOWER_MAX
                               for item in t.items)]
        assert len(flower_tiles) > 0, "Enhancement should produce flower items"


# ===========================================================================
# Test: Hedge rows
# ===========================================================================

class TestHedgeRows:
    def test_hedge_row_items(self):
        """Hedge row should place hedge items."""
        map_data = _make_plain_map()
        gen = VegetationEnhancer(map_data=map_data, num_hedge_rows=1, seed=42,
                                  num_tree_clusters=0, flower_density=0)
        result = gen.enhance()

        hedge_tiles = [t for t in result.tiles
                       if any(item.id == VegTiles.HEDGE for item in t.items)]
        assert len(hedge_tiles) > 0, "Hedge row should place hedge items"

    def test_hedge_row_horizontal(self):
        """Horizontal hedge should extend along x-axis."""
        map_data = _make_plain_map(60, 60)
        gen = VegetationEnhancer(map_data=map_data, seed=42)
        result = gen.place_hedge_row((10, 10), direction="h")

        hedge_tiles = [t for t in result.tiles
                       if any(item.id == VegTiles.HEDGE for item in t.items)]
        # All hedge tiles should have y=10
        for ht in hedge_tiles:
            assert ht.y == 10, f"Hedge tile at {ht.x},{ht.y} should be on row y=10"

    def test_hedge_row_vertical(self):
        """Vertical hedge should extend along y-axis."""
        map_data = _make_plain_map(60, 60)
        gen = VegetationEnhancer(map_data=map_data, seed=42)
        result = gen.place_hedge_row((10, 10), direction="v")

        hedge_tiles = [t for t in result.tiles
                       if any(item.id == VegTiles.HEDGE for item in t.items)]
        # All hedge tiles should have x=10
        for ht in hedge_tiles:
            assert ht.x == 10, f"Hedge tile at {ht.x},{ht.y} should be on column x=10"

    def test_hedge_row_length(self):
        """Hedge row length should be limited by hedge_length parameter."""
        map_data = _make_plain_map(100, 100)
        gen = VegetationEnhancer(map_data=map_data, seed=42, hedge_length=8)
        result = gen.place_hedge_row((10, 10), direction="h")

        hedge_tiles = [t for t in result.tiles
                       if any(item.id == VegTiles.HEDGE for item in t.items)]
        assert len(hedge_tiles) <= 8, f"Hedge row should be at most 8 tiles, got {len(hedge_tiles)}"


# ===========================================================================
# Test: Grass variation
# ===========================================================================

class TestGrassVariation:
    def test_grass_variation_applied(self):
        """Enhancement should vary grass tiles."""
        map_data = _make_plain_map()
        gen = VegetationEnhancer(map_data=map_data, add_grass_variation=True, seed=42,
                                  num_tree_clusters=0, num_hedge_rows=0, flower_density=0)
        result = gen.enhance()

        # Should have some non-default grass variants (dark or meadow, not light=102)
        variants = {VegTiles.GRASS_DARK, VegTiles.GRASS_MEADOW}
        variant_tiles = [t for t in result.tiles if t.ground_id in variants]
        assert len(variant_tiles) > 0, "Should have grass variant tiles"

    def test_no_variation_when_disabled(self):
        """No grass variation when add_grass_variation=False."""
        map_data = _make_plain_map()
        gen = VegetationEnhancer(map_data=map_data, add_grass_variation=False, seed=42,
                                  num_tree_clusters=0, num_hedge_rows=0, flower_density=0)
        result = gen.enhance()

        # Only non-default variants should be 0
        variants = {VegTiles.GRASS_DARK, VegTiles.GRASS_MEADOW}
        variant_tiles = [t for t in result.tiles if t.ground_id in variants]
        assert len(variant_tiles) == 0, "No grass variants when disabled"


# ===========================================================================
# Test: Density configuration
# ===========================================================================

class TestDensity:
    def test_higher_density_more_trees(self):
        """Higher tree density should produce more trees across the full enhance."""
        map_data = _make_plain_map(60, 60)
        gen_low = VegetationEnhancer(map_data=map_data, tree_density=0.01, seed=42,
                                      num_tree_clusters=5, flower_density=0, num_hedge_rows=0)
        gen_high = VegetationEnhancer(map_data=map_data, tree_density=0.8, seed=42,
                                       num_tree_clusters=5, flower_density=0, num_hedge_rows=0)
        result_low = gen_low.enhance()
        result_high = gen_high.enhance()

        trees_low = len([t for t in result_low.tiles
                         if any(VegTiles.TREE_MIN <= item.id <= VegTiles.TREE_MAX
                                for item in t.items)])
        trees_high = len([t for t in result_high.tiles
                          if any(VegTiles.TREE_MIN <= item.id <= VegTiles.TREE_MAX
                                 for item in t.items)])
        assert trees_high > trees_low, f"High density ({trees_high}) should > low ({trees_low})"
