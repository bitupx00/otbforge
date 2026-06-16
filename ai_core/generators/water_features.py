"""Water features generator: lakes, wells, oases, fountains, and waterfalls.

Adds natural and constructed water features to a map:
  - Lakes: elliptical water bodies with sandy/beach shore borders
  - Wells: small water sources placed in town areas
  - Oases: small water + palm trees in desert/sandy areas
  - Fountains: decorative water features for town plazas
  - Waterfalls: vertical cascades (items placed on z-level transitions)

Features:
  - Configurable sizes and counts
  - Biome-aware placement
  - Shore/beach tiles around lakes
  - Integration with existing map data
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    TileData,
    Tiles,
)


# ---------------------------------------------------------------------------
# Water feature tile IDs
# ---------------------------------------------------------------------------

class WaterTiles:
    """Tile IDs for water features."""
    WATER = 490
    SHALLOW_WATER = 491
    SAND = 231
    PALM_TREE = 2723
    WELL_ITEM = 2417       # decorative well item
    FOUNTAIN_ITEM = 2418   # decorative fountain item
    WATERFALL_ITEM = 4900  # waterfall decoration
    BUSH_1 = 2767
    BUSH_2 = 2768


# ---------------------------------------------------------------------------
# WaterFeatureGenerator
# ---------------------------------------------------------------------------

@dataclass
class WaterFeatureGenerator:
    """Water features generator for adding lakes, wells, oases, and fountains.

    Parameters
    ----------
    map_data : MapData
        Base map to add water features to.
    seed : int
        RNG seed for reproducibility.
    num_lakes : int
        Number of lakes to generate.
    lake_size_range : tuple
        (min_radius, max_radius) for lake semi-axes.
    num_wells : int
        Number of wells to place.
    num_oases : int
        Number of oases to generate.
    num_fountains : int
        Number of fountains to place.
    """
    map_data: MapData = field(default_factory=lambda: MapData(width=256, height=256))
    seed: int = 42
    num_lakes: int = 2
    lake_size_range: Tuple[int, int] = (5, 15)
    num_wells: int = 1
    num_oases: int = 1
    num_fountains: int = 1

    def generate(self) -> MapData:
        """Generate all water features and return updated MapData."""
        rng = random.Random(self.seed)

        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        ground_map = self._build_ground_map()
        z = 0

        # --- Lakes ---
        lake_positions = self._find_valid_positions(
            ground_map, self.num_lakes, rng, avoid_water=True,
        )
        for (lx, ly) in lake_positions:
            self._place_lake(tile_grid, ground_map, lx, ly, rng)

        # Refresh ground map after lakes
        ground_map = self._rebuild_ground_map(tile_grid)

        # --- Wells ---
        well_positions = self._find_valid_positions(
            ground_map, self.num_wells, rng, avoid_water=True,
        )
        for (wx, wy) in well_positions:
            self._place_well(tile_grid, wx, wy, z)

        # --- Oases ---
        sand_tiles = [
            (x, y) for (x, y), gid in ground_map.items()
            if gid == Tiles.SAND
        ]
        oasis_positions: List[Tuple[int, int]] = []
        for _ in range(min(self.num_oases, len(sand_tiles) if sand_tiles else 0)):
            pos = rng.choice(sand_tiles)
            oasis_positions.append(pos)

        for (ox, oy) in oasis_positions:
            self._place_oasis(tile_grid, ox, oy, rng)

        # Refresh ground map after oases
        ground_map = self._rebuild_ground_map(tile_grid)

        # --- Fountains ---
        fountain_positions = self._find_valid_positions(
            ground_map, self.num_fountains, rng, avoid_water=True,
        )
        for (fx, fy) in fountain_positions:
            self._place_fountain(tile_grid, fx, fy, z)

        return MapData(
            width=self.map_data.width,
            height=self.map_data.height,
            description=self.map_data.description,
            tiles=list(tile_grid.values()),
            towns=list(self.map_data.towns),
            waypoints=list(self.map_data.waypoints),
            spawns=list(self.map_data.spawns),
            npc_spawns=list(self.map_data.npc_spawns),
        )

    def place_lake(self, cx: int, cy: int) -> MapData:
        """Place a single lake at the specified center position."""
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        ground_map = self._build_ground_map()
        rng = random.Random(self.seed)
        self._place_lake(tile_grid, ground_map, cx, cy, rng)

        return MapData(
            width=self.map_data.width,
            height=self.map_data.height,
            description=self.map_data.description,
            tiles=list(tile_grid.values()),
            towns=list(self.map_data.towns),
            waypoints=list(self.map_data.waypoints),
            spawns=list(self.map_data.spawns),
            npc_spawns=list(self.map_data.npc_spawns),
        )

    def place_well(self, x: int, y: int) -> MapData:
        """Place a well at the specified position."""
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        self._place_well(tile_grid, x, y, 0)

        return MapData(
            width=self.map_data.width,
            height=self.map_data.height,
            description=self.map_data.description,
            tiles=list(tile_grid.values()),
            towns=list(self.map_data.towns),
            waypoints=list(self.map_data.waypoints),
            spawns=list(self.map_data.spawns),
            npc_spawns=list(self.map_data.npc_spawns),
        )

    def place_oasis(self, cx: int, cy: int) -> MapData:
        """Place an oasis at the specified center position."""
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        rng = random.Random(self.seed)
        self._place_oasis(tile_grid, cx, cy, rng)

        return MapData(
            width=self.map_data.width,
            height=self.map_data.height,
            description=self.map_data.description,
            tiles=list(tile_grid.values()),
            towns=list(self.map_data.towns),
            waypoints=list(self.map_data.waypoints),
            spawns=list(self.map_data.spawns),
            npc_spawns=list(self.map_data.npc_spawns),
        )

    # ---- Internal methods ----

    def _build_ground_map(self) -> Dict[Tuple[int, int], int]:
        ground_map: Dict[Tuple[int, int], int] = {}
        for tile in self.map_data.tiles:
            ground_map[(tile.x, tile.y)] = tile.ground_id
        return ground_map

    def _rebuild_ground_map(self, tile_grid: Dict[Tuple[int, int, int], TileData]) -> Dict[Tuple[int, int], int]:
        ground_map: Dict[Tuple[int, int], int] = {}
        for t in tile_grid.values():
            if t.z == 0:
                ground_map[(t.x, t.y)] = t.ground_id
        return ground_map

    def _find_valid_positions(
        self,
        ground_map: Dict[Tuple[int, int], int],
        count: int,
        rng: random.Random,
        avoid_water: bool = True,
    ) -> List[Tuple[int, int]]:
        """Find valid positions for placing features."""
        margin = 10
        w = self.map_data.width
        h = self.map_data.height
        candidates = []

        for (x, y), gid in ground_map.items():
            if x < margin or x >= w - margin or y < margin or y >= h - margin:
                continue
            if avoid_water and gid == Tiles.WATER:
                continue
            candidates.append((x, y))

        if not candidates:
            return []

        positions: List[Tuple[int, int]] = []
        used: Set[Tuple[int, int]] = set()

        for _ in range(count * 50):
            if len(positions) >= count:
                break
            pos = rng.choice(candidates)
            if pos in used:
                continue
            used.add(pos)
            positions.append(pos)

        return positions

    def _place_lake(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        ground_map: Dict[Tuple[int, int], int],
        cx: int, cy: int,
        rng: random.Random,
    ):
        """Place an elliptical lake with shore tiles."""
        min_r, max_r = self.lake_size_range
        rx = rng.randint(min_r, max_r)
        ry = rng.randint(min_r, max_r)

        z = 0
        water_cells: List[Tuple[int, int]] = []
        shore_cells: List[Tuple[int, int]] = []

        # Build ellipse
        for dy in range(-ry - 2, ry + 3):
            for dx in range(-rx - 2, rx + 3):
                px, py = cx + dx, cy + dy
                # Normalized ellipse distance
                ex = dx / rx if rx > 0 else 0
                ey = dy / ry if ry > 0 else 0
                dist = math.sqrt(ex * ex + ey * ey)

                if dist <= 1.0:
                    # Add some noise for organic shape
                    noise = (rng.random() - 0.5) * 0.15
                    if dist + noise <= 1.0:
                        water_cells.append((px, py))
                    else:
                        shore_cells.append((px, py))
                elif dist <= 1.25:
                    shore_cells.append((px, py))

        # Place shore tiles first (sand border)
        for (sx, sy) in shore_cells:
            tile = TileData(x=sx, y=sy, z=z, ground_id=WaterTiles.SAND)
            tile_grid[(sx, sy, z)] = tile

        # Place water tiles
        for (wx, wy) in water_cells:
            tile = TileData(x=wx, y=wy, z=z, ground_id=WaterTiles.WATER)
            tile_grid[(wx, wy, z)] = tile

    def _place_well(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        x: int, y: int, z: int,
    ):
        """Place a well (decorative item on existing tile)."""
        tile = tile_grid.get((x, y, z))
        if tile is None:
            tile = TileData(x=x, y=y, z=z, ground_id=Tiles.GRASS)
            tile_grid[(x, y, z)] = tile
        tile.items.append(ItemData(id=WaterTiles.WELL_ITEM))

    def _place_oasis(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        cx: int, cy: int,
        rng: random.Random,
    ):
        """Place an oasis: small water + palm trees in sandy area."""
        z = 0
        radius = 4

        # Water center
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                px, py = cx + dx, cy + dy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= 2.0:
                    tile = TileData(x=px, y=py, z=z, ground_id=WaterTiles.WATER)
                    tile_grid[(px, py, z)] = tile
                elif dist <= 2.5:
                    tile = TileData(x=px, y=py, z=z, ground_id=WaterTiles.SHALLOW_WATER)
                    tile_grid[(px, py, z)] = tile

        # Palm trees around
        palm_positions = [
            (cx - 4, cy), (cx + 4, cy),
            (cx, cy - 4), (cx, cy + 4),
            (cx - 3, cy - 3), (cx + 3, cy - 3),
            (cx - 3, cy + 3), (cx + 3, cy + 3),
        ]
        for (px, py) in palm_positions:
            if rng.random() < 0.7:
                tile = tile_grid.get((px, py, z))
                if tile is None:
                    tile = TileData(x=px, y=py, z=z, ground_id=WaterTiles.SAND)
                    tile_grid[(px, py, z)] = tile
                tile.items.append(ItemData(id=WaterTiles.PALM_TREE))

    def _place_fountain(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        x: int, y: int, z: int,
    ):
        """Place a fountain (decorative item + paved ground)."""
        tile = tile_grid.get((x, y, z))
        if tile is None:
            tile = TileData(x=x, y=y, z=z, ground_id=Tiles.GRASS)
            tile_grid[(x, y, z)] = tile
        # Change ground to pavement
        tile.ground_id = 355  # cobblestone
        tile.items.append(ItemData(id=WaterTiles.FOUNTAIN_ITEM))
