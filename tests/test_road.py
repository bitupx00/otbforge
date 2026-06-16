"""Tests for road/path generator: A* pathfinding, bridges, width, multi-path network."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.otbm_types import MapData, TileData, Tiles
from ai_core.generators.road_generator import RoadGenerator, RoadTiles


# ===========================================================================
# Helper to create simple test maps
# ===========================================================================

def _make_plain_map(w=50, h=50, ground=Tiles.GRASS) -> MapData:
    """Create a simple map filled with the given ground tile."""
    tiles = [TileData(x=x, y=y, z=0, ground_id=ground) for x in range(w) for y in range(h)]
    return MapData(width=w, height=h, tiles=tiles, description="test")


def _make_map_with_water(w=50, h=50, water_y=25) -> MapData:
    """Create a map with a horizontal water strip."""
    tiles = []
    for x in range(w):
        for y in range(h):
            gid = Tiles.WATER if y == water_y else Tiles.GRASS
            tiles.append(TileData(x=x, y=y, z=0, ground_id=gid))
    return MapData(width=w, height=h, tiles=tiles, description="test")


def _make_map_with_obstacles(w=50, h=50) -> MapData:
    """Create a map with water obstacles."""
    tiles = []
    for x in range(w):
        for y in range(h):
            # Water wall from y=20 to y=25
            gid = Tiles.WATER if 20 <= y <= 22 else Tiles.GRASS
            tiles.append(TileData(x=x, y=y, z=0, ground_id=gid))
    return MapData(width=w, height=h, tiles=tiles, description="test")


# ===========================================================================
# Test: A* pathfinding
# ===========================================================================

class TestRoadPathfinding:
    def test_path_exists_on_plain_map(self):
        """A* should find a path on an obstacle-free map."""
        gen = RoadGenerator(map_data=_make_plain_map())
        path = gen.generate_path((5, 5), (40, 40))
        assert len(path) > 0, "Path should exist on plain map"
        assert path[0] == (5, 5), "Path should start at origin"
        assert path[-1] == (40, 40), "Path should end at destination"

    def test_path_connected(self):
        """Each step in the path should be adjacent to the next."""
        gen = RoadGenerator(map_data=_make_plain_map(), smooth_path=False)
        path = gen.generate_path((5, 5), (30, 30))
        for i in range(len(path) - 1):
            dx = abs(path[i + 1][0] - path[i][0])
            dy = abs(path[i + 1][1] - path[i][1])
            assert dx <= 1 and dy <= 1, f"Non-adjacent step at index {i}: {path[i]} -> {path[i + 1]}"

    def test_path_avoids_mountains(self):
        """Path should avoid mountain tiles when avoid_mountains=True."""
        tiles = []
        for x in range(50):
            for y in range(50):
                gid = 919 if 20 <= y <= 22 else Tiles.GRASS  # 919 = mountain
                tiles.append(TileData(x=x, y=y, z=0, ground_id=gid))
        map_data = MapData(width=50, height=50, tiles=tiles)
        gen = RoadGenerator(map_data=map_data, avoid_mountains=True)
        path = gen.generate_path((10, 10), (40, 40))
        # Path should go around the mountains (y < 20 or y > 22)
        mountain_steps = [(x, y) for x, y in path if 20 <= y <= 22]
        assert len(mountain_steps) == 0, f"Path stepped on mountain tiles: {mountain_steps}"


# ===========================================================================
# Test: Bridges
# ===========================================================================

class TestRoadBridges:
    def test_bridge_over_water_strip(self):
        """Road should use bridge tiles when crossing water with avoid_water=False."""
        map_data = _make_map_with_water(50, 50, water_y=25)
        gen = RoadGenerator(map_data=map_data, avoid_water=False, smooth_path=False)
        path = gen.generate_path((25, 5), (25, 45))
        assert len(path) > 0, "Path should cross water when avoid_water=False"

        # Verify path crosses water row
        water_crossings = [(x, y) for x, y in path if y == 25]
        assert len(water_crossings) > 0, "Path should cross water at y=25"

        result = gen.apply_path(path)
        # Check that water tiles were changed to road or bridge
        road_or_bridge = [t for t in result.tiles
                          if t.y == 25 and t.x == 25 and
                          t.ground_id in (RoadTiles.BRIDGE_H, RoadTiles.BRIDGE_V, RoadTiles.COBBLESTONE)]
        assert len(road_or_bridge) > 0, "Water crossing should have road/bridge tiles"

    def test_bridge_tiles_on_water(self):
        """Bridge tiles should only appear where water was."""
        map_data = _make_map_with_water(50, 50, water_y=25)
        gen = RoadGenerator(map_data=map_data, avoid_water=False)
        path = gen.generate_path((10, 5), (10, 45))
        result = gen.apply_path(path)

        bridge_tiles = [t for t in result.tiles
                        if t.ground_id in (RoadTiles.BRIDGE_H, RoadTiles.BRIDGE_V)]
        for bt in bridge_tiles:
            # Original map had water at y=25
            assert bt.y == 25, f"Bridge tile at {bt.x},{bt.y} should be on water row"


# ===========================================================================
# Test: Road width
# ===========================================================================

class TestRoadWidth:
    def test_width_1_single_tile(self):
        """Width 1 should place exactly one tile per path point."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data, width=1, smooth_path=False)
        path = gen.generate_path((5, 5), (10, 5))
        result = gen.apply_path(path)

        road_tiles = [t for t in result.tiles if t.ground_id == gen.road_tile]
        assert len(road_tiles) == len(path), "Width 1 should have exactly one tile per path point"

    def test_width_2_expands_path(self):
        """Width 2 should place more tiles than width 1."""
        map_data = _make_plain_map()
        gen1 = RoadGenerator(map_data=_make_plain_map(), width=1, smooth_path=False)
        gen2 = RoadGenerator(map_data=_make_plain_map(), width=2, smooth_path=False)
        path = gen1.generate_path((5, 5), (20, 20))

        result1 = gen1.apply_path(path)
        result2_tiles_count = len([t for t in gen2.apply_path(path).tiles
                                   if t.ground_id == gen2.road_tile])

        result1_tiles_count = len([t for t in result1.tiles
                                   if t.ground_id == gen1.road_tile])
        assert result2_tiles_count >= result1_tiles_count, "Width 2 should have >= tiles than width 1"


# ===========================================================================
# Test: Multi-path network
# ===========================================================================

class TestRoadNetwork:
    def test_network_connects_all_waypoints(self):
        """Network should produce paths connecting all waypoints."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data)
        waypoints = [(10, 10), (40, 10), (25, 40)]
        paths = gen.generate_network(waypoints)

        # With 3 waypoints, MST should have 2 edges
        assert len(paths) == 2, "MST with 3 nodes should have 2 edges"

        # Each path should be non-empty
        for path in paths:
            assert len(path) > 0, "Each network path should be non-empty"

    def test_network_empty_single_waypoint(self):
        """Network with single waypoint should return empty list."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data)
        paths = gen.generate_network([(25, 25)])
        assert paths == [], "Single waypoint should produce no paths"

    def test_network_empty_no_waypoints(self):
        """Network with no waypoints should return empty list."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data)
        paths = gen.generate_network([])
        assert paths == [], "No waypoints should produce no paths"

    def test_network_four_waypoints(self):
        """Network with 4 waypoints should have 3 edges."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data)
        waypoints = [(10, 10), (40, 10), (10, 40), (40, 40)]
        paths = gen.generate_network(waypoints)
        assert len(paths) == 3, "MST with 4 nodes should have 3 edges"


# ===========================================================================
# Test: Path smoothing
# ===========================================================================

class TestPathSmoothing:
    def test_smoothed_path_shorter(self):
        """Smoothed path should be shorter or equal to raw path."""
        map_data = _make_plain_map()
        gen_raw = RoadGenerator(map_data=map_data, smooth_path=False)
        gen_smooth = RoadGenerator(map_data=map_data, smooth_path=True)
        path_raw = gen_raw.generate_path((5, 5), (45, 45))
        path_smooth = gen_smooth.generate_path((5, 5), (45, 45))
        assert len(path_smooth) <= len(path_raw), "Smoothed path should be shorter"


# ===========================================================================
# Test: Road tile types
# ===========================================================================

class TestRoadTiles:
    def test_default_road_tile(self):
        """Default road tile should be cobblestone."""
        assert RoadTiles.COBBLESTONE == 355
        assert RoadTiles.STONE_PATH == 356
        assert RoadTiles.PAVED_ROAD == 357

    def test_bridge_tiles(self):
        """Bridge tiles should have expected IDs."""
        assert RoadTiles.BRIDGE_H == 5408
        assert RoadTiles.BRIDGE_V == 5409

    def test_custom_road_tile(self):
        """Should use custom road tile when specified."""
        map_data = _make_plain_map()
        gen = RoadGenerator(map_data=map_data, road_tile=RoadTiles.PAVED_ROAD)
        path = gen.generate_path((10, 10), (15, 10))
        result = gen.apply_path(path)
        road_tiles = [t for t in result.tiles if t.ground_id == RoadTiles.PAVED_ROAD]
        assert len(road_tiles) > 0, "Custom road tile should be used"
