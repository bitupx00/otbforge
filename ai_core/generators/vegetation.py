"""Vegetation enhancer for adding natural plant life to maps.

Enhances maps with clustered vegetation that looks natural rather than
randomly scattered individual trees:
  - Tree clusters (forests, groves) with configurable density
  - Meadow flower patches (concentrated flower areas)
  - Bush/hedge rows for zone delimiting
  - Grass variation (different grass types per area)
  - Biome-aware density configuration

Features:
  - Cluster-based placement (not random scattered)
  - Density configurable per zone/region
  - Hedge rows for fences and borders
  - Multiple grass tile variations
  - Seed-based deterministic generation
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
# Vegetation tile IDs
# ---------------------------------------------------------------------------

class VegTiles:
    """Tile IDs for vegetation generation."""
    # Trees
    TREE_MIN = 2700
    TREE_MAX = 2708
    OAK = 2700
    PINE = 2703
    WILLOW = 2705
    PALM = 2723

    # Bushes
    BUSH_1 = 2767
    BUSH_2 = 2768

    # Flowers
    FLOWER_MIN = 2740
    FLOWER_MAX = 2743
    ROSE = 2740
    TULIP = 2741

    # Grass variants
    GRASS_LIGHT = 102
    GRASS_DARK = 103
    GRASS_MEADOW = 3019
    GRASS_SWAMP = 3653
    GRASS_JUNGLE = 3611

    # Hedge / border
    HEDGE = 2786


# ---------------------------------------------------------------------------
# VegetationEnhancer
# ---------------------------------------------------------------------------

@dataclass
class VegetationEnhancer:
    """Vegetation enhancer that adds natural plant clusters to maps.

    Parameters
    ----------
    map_data : MapData
        Base map to enhance with vegetation.
    seed : int
        RNG seed for reproducibility.
    tree_density : float
        Tree placement probability per walkable tile (0.0 - 1.0).
    flower_density : float
        Flower placement probability per walkable tile.
    bush_density : float
        Bush placement probability per walkable tile.
    num_tree_clusters : int
        Number of tree cluster centers to generate.
    cluster_radius : int
        Maximum radius of a tree cluster.
    num_hedge_rows : int
        Number of hedge rows to place.
    hedge_length : int
        Maximum length of a hedge row.
    add_grass_variation : bool
        Whether to vary grass tile types.
    """
    map_data: MapData = field(default_factory=lambda: MapData(width=256, height=256))
    seed: int = 42
    tree_density: float = 0.15
    flower_density: float = 0.08
    bush_density: float = 0.05
    num_tree_clusters: int = 8
    cluster_radius: int = 10
    num_hedge_rows: int = 2
    hedge_length: int = 20
    add_grass_variation: bool = True

    # Tiles to skip (no vegetation on these)
    SKIP_GROUND: Set[int] = field(default_factory=lambda: {
        Tiles.WATER, Tiles.LAVA, Tiles.STONE_WALL, Tiles.SAND,
    })

    def enhance(self) -> MapData:
        """Apply all vegetation enhancements and return updated MapData."""
        rng = random.Random(self.seed)

        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        ground_map = self._build_ground_map()

        # --- Tree clusters ---
        walkable = [
            (x, y) for (x, y), gid in ground_map.items()
            if gid not in self.SKIP_GROUND and gid > 0
        ]

        cluster_centers = self._pick_cluster_centers(walkable, rng)
        for (cx, cy) in cluster_centers:
            self._place_tree_cluster(tile_grid, cx, cy, rng)

        # --- Meadow flower patches ---
        flower_centers = self._pick_cluster_centers(walkable, rng, count=max(1, self.num_tree_clusters // 2))
        for (fx, fy) in flower_centers:
            self._place_flower_patch(tile_grid, fx, fy, rng)

        # --- Hedge rows ---
        for _ in range(self.num_hedge_rows):
            if walkable:
                start = rng.choice(walkable)
                self._place_hedge_row(tile_grid, start, rng)

        # --- Grass variation ---
        if self.add_grass_variation:
            self._apply_grass_variation(tile_grid, ground_map, rng)

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

    def place_tree_cluster(self, cx: int, cy: int, radius: int = 0) -> MapData:
        """Place a single tree cluster at the specified center.

        If radius is 0, uses self.cluster_radius.
        """
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        rng = random.Random(self.seed)
        self._place_tree_cluster(tile_grid, cx, cy, rng, override_radius=radius or self.cluster_radius)

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

    def place_hedge_row(self, start: Tuple[int, int], direction: str = "h") -> MapData:
        """Place a hedge row starting from the given position.

        direction: 'h' for horizontal, 'v' for vertical.
        """
        tile_grid: Dict[Tuple[int, int, int], TileData] = {}
        for t in self.map_data.tiles:
            tile_grid[(t.x, t.y, t.z)] = t

        rng = random.Random(self.seed)
        self._place_hedge_row_directed(tile_grid, start, rng, direction)

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

    def _pick_cluster_centers(
        self,
        walkable: List[Tuple[int, int]],
        rng: random.Random,
        count: int = 0,
        min_spacing: int = 15,
    ) -> List[Tuple[int, int]]:
        """Pick well-spaced cluster center positions."""
        if count == 0:
            count = self.num_tree_clusters

        centers: List[Tuple[int, int]] = []
        for _ in range(count * 20):
            if len(centers) >= count:
                break
            if not walkable:
                break
            pos = rng.choice(walkable)
            if all(math.hypot(pos[0] - cx, pos[1] - cy) >= min_spacing
                   for cx, cy in centers):
                centers.append(pos)

        return centers

    def _place_tree_cluster(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        cx: int, cy: int,
        rng: random.Random,
        override_radius: int = 0,
    ):
        """Place a circular cluster of trees around (cx, cy)."""
        z = 0
        radius = override_radius or self.cluster_radius

        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > radius:
                    continue

                px, py = cx + dx, cy + dy

                # Density decreases with distance from center
                density = self.tree_density * (1.0 - dist / (radius + 1))

                # Deterministic per-position
                local_rng = random.Random(self.seed + px * 73856093 + py * 19349663)
                roll = local_rng.random()

                if roll < density:
                    tile = tile_grid.get((px, py, z))
                    if tile is None:
                        tile = TileData(x=px, y=py, z=z, ground_id=Tiles.GRASS)
                        tile_grid[(px, py, z)] = tile

                    # Pick tree type (mix of available trees)
                    tree_id = rng.randint(VegTiles.TREE_MIN, VegTiles.TREE_MAX)
                    tile.items.append(ItemData(id=tree_id))

                # Occasional bushes at cluster edge
                elif roll < density + self.bush_density and dist > radius * 0.5:
                    tile = tile_grid.get((px, py, z))
                    if tile is None:
                        tile = TileData(x=px, y=py, z=z, ground_id=Tiles.GRASS)
                        tile_grid[(px, py, z)] = tile
                    bush_id = rng.choice([VegTiles.BUSH_1, VegTiles.BUSH_2])
                    tile.items.append(ItemData(id=bush_id))

    def _place_flower_patch(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        cx: int, cy: int,
        rng: random.Random,
        patch_radius: int = 6,
    ):
        """Place a meadow flower patch."""
        z = 0

        for dy in range(-patch_radius, patch_radius + 1):
            for dx in range(-patch_radius, patch_radius + 1):
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > patch_radius:
                    continue

                px, py = cx + dx, cy + dy

                # Higher density near center
                density = self.flower_density * (1.2 - dist / (patch_radius + 1))

                local_rng = random.Random(self.seed + px * 83492791 + py * 57349669)
                roll = local_rng.random()

                if roll < density:
                    tile = tile_grid.get((px, py, z))
                    if tile is None:
                        tile = TileData(x=px, y=py, z=z, ground_id=Tiles.GRASS)
                        tile_grid[(px, py, z)] = tile
                    flower_id = rng.randint(VegTiles.FLOWER_MIN, VegTiles.FLOWER_MAX)
                    tile.items.append(ItemData(id=flower_id))

    def _place_hedge_row(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        start: Tuple[int, int],
        rng: random.Random,
    ):
        """Place a hedge row in a random direction."""
        direction = rng.choice(["h", "v"])
        self._place_hedge_row_directed(tile_grid, start, rng, direction)

    def _place_hedge_row_directed(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        start: Tuple[int, int],
        rng: random.Random,
        direction: str,
    ):
        """Place a hedge row in a specific direction."""
        z = 0
        sx, sy = start
        length = rng.randint(5, self.hedge_length)

        for i in range(length):
            if direction == "h":
                px, py = sx + i, sy
            else:
                px, py = sx, sy + i

            if px < 0 or px >= self.map_data.width or py < 0 or py >= self.map_data.height:
                continue

            tile = tile_grid.get((px, py, z))
            if tile is None:
                tile = TileData(x=px, y=py, z=z, ground_id=Tiles.GRASS)
                tile_grid[(px, py, z)] = tile

            # Only place if not on road/water
            if tile.ground_id not in self.SKIP_GROUND:
                tile.items.append(ItemData(id=VegTiles.HEDGE))

    def _apply_grass_variation(
        self,
        tile_grid: Dict[Tuple[int, int, int], TileData],
        ground_map: Dict[Tuple[int, int], int],
        rng: random.Random,
    ):
        """Vary grass tiles for more natural look."""
        z = 0
        grass_variants = [VegTiles.GRASS_LIGHT, VegTiles.GRASS_DARK, VegTiles.GRASS_MEADOW]

        for (x, y), gid in ground_map.items():
            if gid == Tiles.GRASS:
                # Use position-based seed for variation
                local_rng = random.Random(self.seed + x * 127 + y * 311)
                roll = local_rng.random()
                if roll < 0.15:
                    variant = local_rng.choice(grass_variants)
                    tile = tile_grid.get((x, y, z))
                    if tile is not None:
                        tile.ground_id = variant
