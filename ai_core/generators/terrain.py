"""Terrain generator using 2D Perlin-like noise with biomes, rivers, and island shape.

Generates a MapData with authentic Tibia tile IDs, suitable for OTBMWriter.
Features:
  - 2+ octave Perlin noise for elevation
  - Moisture noise (second seed) for biomes
  - Organic island shape (ellipse + noise falloff)
  - 11 biome types based on elevation + moisture
  - River carving from mountains toward ocean
  - Deterministic seed-based generation
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    Position,
    TileData,
    Tiles,
)


# ---------------------------------------------------------------------------
# Tibia-authentic Tile IDs (supplement to Tiles in otbm_types)
# ---------------------------------------------------------------------------

class TerrainTiles:
    """Authentic Tibia tile IDs for terrain generation."""
    WATER        = 490
    SHALLOW_WATER = 491
    SAND         = 231
    GRASS        = 102
    DIRT         = 2021
    ROCK_SOIL    = 107
    MOUNTAIN     = 919
    SNOW         = 7932
    LAVA         = 493
    SWAMP_GRASS  = 3653
    JUNGLE_GRASS = 3611
    RIVER        = 4608

    # Vegetation
    TREE_MIN     = 2700
    TREE_MAX     = 2708
    BUSH_1       = 2767
    BUSH_2       = 2768
    FLOWER_MIN   = 2740
    FLOWER_MAX   = 2743

    # Dungeon tiles (reused here for completeness)
    STONE_FLOOR_MIN = 410
    STONE_FLOOR_MAX = 416


# ---------------------------------------------------------------------------
# Biome enum
# ---------------------------------------------------------------------------

class Biome:
    """Biome classification constants."""
    DEEP_WATER   = "deep_water"
    SHALLOW_WATER = "shallow_water"
    BEACH        = "beach"
    PLAINS       = "plains"
    FOREST       = "forest"
    DENSE_FOREST = "dense_forest"
    HILLS        = "hills"
    MOUNTAINS    = "mountains"
    SNOW_PEAKS   = "snow_peaks"
    SWAMP        = "swamp"
    JUNGLE       = "jungle"


# ---------------------------------------------------------------------------
# Biome → ground tile mapping
# ---------------------------------------------------------------------------

BIOME_GROUND: Dict[str, int] = {
    Biome.DEEP_WATER:    TerrainTiles.WATER,
    Biome.SHALLOW_WATER: TerrainTiles.WATER,
    Biome.BEACH:         TerrainTiles.SAND,
    Biome.PLAINS:        TerrainTiles.GRASS,
    Biome.FOREST:        TerrainTiles.GRASS,
    Biome.DENSE_FOREST:  TerrainTiles.GRASS,
    Biome.HILLS:         TerrainTiles.ROCK_SOIL,
    Biome.MOUNTAINS:     TerrainTiles.MOUNTAIN,
    Biome.SNOW_PEAKS:    TerrainTiles.SNOW,
    Biome.SWAMP:         TerrainTiles.SWAMP_GRASS,
    Biome.JUNGLE:        TerrainTiles.JUNGLE_GRASS,
}


# ---------------------------------------------------------------------------
# Perlin-like value-noise implementation (no external deps)
# ---------------------------------------------------------------------------

def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    return a + t * (b - a)


def _hash2d(ix: int, iy: int, seed: int) -> float:
    """Deterministic hash of (ix, iy, seed) -> [0, 1)."""
    n = ix * 374761393 + iy * 668265263 + seed * 1274126177
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    n = (n ^ (n >> 16)) & 0xFFFFFFFF
    return (n & 0xFFFF) / 0xFFFF


def _gradient_noise(x: float, y: float, seed: int) -> float:
    """Smooth value noise with bilinear interpolation."""
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    u = _fade(fx)
    v = _fade(fy)
    a = _lerp(_hash2d(ix, iy, seed), _hash2d(ix + 1, iy, seed), u)
    b = _lerp(_hash2d(ix, iy + 1, seed), _hash2d(ix + 1, iy + 1, seed), u)
    return _lerp(a, b, v)


def perlin_2d(x: float, y: float, seed: int, octaves: int = 4,
              persistence: float = 0.5, lacunarity: float = 2.0) -> float:
    """Fractal Brownian motion on top of value noise. Returns ~[0, 1]."""
    total = 0.0
    amplitude = 1.0
    frequency = 1.0
    max_val = 0.0
    for _ in range(octaves):
        total += _gradient_noise(x * frequency, y * frequency, seed) * amplitude
        max_val += amplitude
        amplitude *= persistence
        frequency *= lacunarity
    return max(0.0, min(1.0, total / max_val))


# ---------------------------------------------------------------------------
# Biome classification
# ---------------------------------------------------------------------------

def classify_biome(elevation: float, moisture: float,
                   water_level: float) -> str:
    """Classify a tile's biome from elevation and moisture values.

    Elevation thresholds (relative to water_level):
      < water_level - 0.05   → deep water
      < water_level          → shallow water
      < water_level + 0.04   → beach
      > 0.82                 → snow peaks
      > 0.65                 → mountains
      > 0.55                 → hills
    Moisture for land tiles:
      > 0.7 + elevation*0.15 → jungle
      > 0.55 + elevation*0.1 → dense forest
      > 0.40                 → forest
      > 0.30                 → plains
      < 0.25                 → swamp (in low elevation areas)
    """
    wl = water_level
    if elevation < wl - 0.05:
        return Biome.DEEP_WATER
    if elevation < wl:
        return Biome.SHALLOW_WATER
    if elevation < wl + 0.04:
        return Biome.BEACH
    if elevation > 0.78:
        return Biome.SNOW_PEAKS
    if elevation > 0.65:
        return Biome.MOUNTAINS
    if elevation > 0.55:
        return Biome.HILLS

    # Land biomes depend on moisture + elevation
    if elevation < wl + 0.12 and moisture > 0.65:
        return Biome.SWAMP
    if moisture > 0.70 + elevation * 0.15:
        return Biome.JUNGLE
    if moisture > 0.55 + elevation * 0.10:
        return Biome.DENSE_FOREST
    if moisture > 0.40:
        return Biome.FOREST
    if moisture > 0.30:
        return Biome.PLAINS
    return Biome.PLAINS


# ---------------------------------------------------------------------------
# TerrainGenerator
# ---------------------------------------------------------------------------

@dataclass
class TerrainGenerator:
    """Procedural terrain generator with Perlin noise, biomes, rivers, and island.

    Parameters
    ----------
    width, height : int
        Map dimensions in tiles.
    seed : int
        RNG seed for reproducible generation.
    water_level : float
        Elevation threshold for water (0–1). Higher = more water.
    biome_scale : float
        Noise scale factor. Lower = larger features.
    octaves : int
        Number of Perlin noise octaves (must be >= 2).
    rivers : bool
        Whether to carve rivers from mountains toward ocean.
    num_rivers : int
        Number of rivers to attempt carving.
    moisture_seed_offset : int
        Offset added to seed for the moisture noise layer.
    """

    width: int = 256
    height: int = 256
    seed: int = 42
    water_level: float = 0.38
    biome_scale: float = 0.02
    octaves: int = 4
    rivers: bool = False
    num_rivers: int = 3
    moisture_seed_offset: int = 1

    def generate(self) -> MapData:
        """Generate the full terrain and return MapData."""
        rng = random.Random(self.seed)
        tiles: List[TileData] = []

        # Pre-compute elevation & moisture grids
        elev: List[List[float]] = []
        moist: List[List[float]] = []
        biomes: List[List[str]] = []

        # First pass: compute raw elevation with falloff
        raw_elev: List[List[float]] = []
        raw_max = 0.0
        for y in range(self.height):
            elev_row: List[float] = []
            moist_row: List[float] = []
            for x in range(self.width):
                nx = x * self.biome_scale
                ny = y * self.biome_scale
                e = perlin_2d(nx, ny, self.seed, octaves=self.octaves)
                edge_dist = self._island_falloff(x, y, self.seed)
                e *= edge_dist
                elev_row.append(e)
                raw_max = max(raw_max, e)

                m = perlin_2d(nx + 100.0, ny + 100.0,
                              self.seed + self.moisture_seed_offset,
                              octaves=2)
                moist_row.append(m)
            raw_elev.append(elev_row)
            moist.append(moist_row)

        # Normalize elevation so max raw value maps to ~0.9
        # This ensures mountains and snow can appear on any map
        if raw_max > 0:
            scale = 0.92 / raw_max
        else:
            scale = 1.0

        for y in range(self.height):
            biome_row: List[str] = []
            scaled_row: List[float] = []
            for x in range(self.width):
                e = raw_elev[y][x] * scale
                m = moist[y][x]
                biome_row.append(classify_biome(e, m, self.water_level))
                scaled_row.append(e)
            elev.append(scaled_row)
            biomes.append(biome_row)

        # Optional rivers
        river_cells: Set[Tuple[int, int]] = set()
        if self.rivers:
            river_cells = self._carve_rivers(elev, biomes, rng)

        # Generate tiles
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in river_cells:
                    ground = TerrainTiles.RIVER
                    items: List[ItemData] = []
                else:
                    biome = biomes[y][x]
                    ground = BIOME_GROUND.get(biome, TerrainTiles.GRASS)
                    items = self._get_vegetation(
                        x, y, biome, elev[y][x], moist[y][x], rng
                    )

                tiles.append(TileData(
                    x=x, y=y, z=0, ground_id=ground, items=items
                ))

        return MapData(
            width=self.width,
            height=self.height,
            description=f"Terrain seed={self.seed}",
            tiles=tiles,
        )

    # ---- Island shape (ellipse + noise) ----

    def _island_falloff(self, x: int, y: int, seed: int) -> float:
        """Compute organic island shape using ellipse + noise perturbation.

        Returns a multiplier in [0, 1] where 0 means ocean edge
        and 1 means full elevation at island centre.
        """
        cx, cy = self.width / 2, self.height / 2
        # Elliptical distance (aspect-ratio corrected) — use 0.46 for wider island
        rx = self.width * 0.46
        ry = self.height * 0.46
        dx = (x - cx) / rx
        dy = (y - cy) / ry
        dist_sq = dx * dx + dy * dy

        # Noise perturbation for organic coastline
        nx = x * self.biome_scale * 0.3
        ny = y * self.biome_scale * 0.3
        coast_noise = perlin_2d(nx, ny, seed + 77777, octaves=3)
        perturbation = (coast_noise - 0.5) * 0.20

        adjusted_dist = math.sqrt(dist_sq) - perturbation
        # Smooth falloff: 1 at center, 0 beyond radius ~1.0
        falloff = max(0.0, 1.0 - adjusted_dist)
        return min(1.0, falloff)

    # ---- River carving ----

    def _carve_rivers(
        self,
        elev: List[List[float]],
        biomes: List[List[str]],
        rng: random.Random,
    ) -> Set[Tuple[int, int]]:
        """Trace rivers from mountain/high areas down toward ocean."""
        cells: Set[Tuple[int, int]] = set()
        w, h = self.width, self.height

        # Find high-elevation start points (mountains / hills near centre)
        starts: List[Tuple[int, int]] = []
        candidates = []
        for y in range(h // 4, 3 * h // 4):
            for x in range(w // 4, 3 * w // 4):
                if elev[y][x] > 0.55 and biomes[y][x] in (
                    Biome.MOUNTAINS, Biome.HILLS, Biome.SNOW_PEAKS
                ):
                    candidates.append((x, y, elev[y][x]))
        # Pick highest points
        candidates.sort(key=lambda c: c[2], reverse=True)
        for cx, cy, _ in candidates[:max(1, self.num_rivers * 3)]:
            # Ensure spatial separation
            if all(abs(cx - sx) > 10 or abs(cy - sy) > 10
                   for sx, sy in starts):
                starts.append((cx, cy))
                if len(starts) >= self.num_rivers:
                    break

        for sx, sy in starts:
            self._trace_river(sx, sy, elev, cells, w, h)

        return cells

    def _trace_river(
        self,
        start_x: int,
        start_y: int,
        elev: List[List[float]],
        cells: Set[Tuple[int, int]],
        w: int,
        h: int,
    ):
        """Trace a single river from high ground toward ocean (gradient descent)."""
        cx, cy = start_x, start_y
        visited: Set[Tuple[int, int]] = set()

        for _ in range(max(w, h) * 2):
            if cx < 0 or cx >= w or cy < 0 or cy >= h:
                break
            if elev[cy][cx] < self.water_level:
                break
            if (cx, cy) in visited:
                break
            visited.add((cx, cy))

            # Carve 1-2 tiles wide
            cells.add((cx, cy))
            if 0 <= cx + 1 < w:
                cells.add((cx + 1, cy))

            # Move toward lowest 8-connected neighbor
            best_elev = float("inf")
            best_x, best_y = cx, cy
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                           (-1, -1), (1, -1), (-1, 1), (1, 1)):
                nx2, ny2 = cx + dx, cy + dy
                if 0 <= nx2 < w and 0 <= ny2 < h:
                    if elev[ny2][nx2] < best_elev:
                        best_elev = elev[ny2][nx2]
                        best_x, best_y = nx2, ny2
            cx, cy = best_x, best_y

    # ---- Vegetation decoration ----

    def _get_vegetation(
        self,
        x: int,
        y: int,
        biome: str,
        elevation: float,
        moisture: float,
        rng: random.Random,
    ) -> List[ItemData]:
        """Generate vegetation items based on biome type."""
        items: List[ItemData] = []

        if biome in (Biome.DEEP_WATER, Biome.SHALLOW_WATER,
                     Biome.BEACH, Biome.MOUNTAINS, Biome.SNOW_PEAKS,
                     Biome.HILLS):
            # No vegetation on water, beach, mountains, snow, hills
            if biome == Biome.HILLS and rng.random() < 0.03:
                items.append(ItemData(id=TerrainTiles.GRASS))
            return items

        # Deterministic per-position random
        rng.seed(self.seed + x * 73856093 + y * 19349663)
        roll = rng.random()

        if biome == Biome.PLAINS:
            # Sparse trees, flowers, occasional bushes
            if roll < 0.02:
                tid = rng.randint(TerrainTiles.TREE_MIN, TerrainTiles.TREE_MAX)
                items.append(ItemData(id=tid))
            elif roll < 0.06:
                fid = rng.randint(TerrainTiles.FLOWER_MIN, TerrainTiles.FLOWER_MAX)
                items.append(ItemData(id=fid))
            elif roll < 0.08:
                items.append(ItemData(id=TerrainTiles.BUSH_1))

        elif biome == Biome.FOREST:
            if roll < 0.12:
                tid = rng.randint(TerrainTiles.TREE_MIN, TerrainTiles.TREE_MAX)
                items.append(ItemData(id=tid))
            elif roll < 0.15:
                items.append(ItemData(id=TerrainTiles.BUSH_1))
            elif roll < 0.17:
                fid = rng.randint(TerrainTiles.FLOWER_MIN, TerrainTiles.FLOWER_MAX)
                items.append(ItemData(id=fid))

        elif biome == Biome.DENSE_FOREST:
            if roll < 0.18:
                tid = rng.randint(TerrainTiles.TREE_MIN, TerrainTiles.TREE_MAX)
                items.append(ItemData(id=tid))
            elif roll < 0.24:
                items.append(ItemData(id=TerrainTiles.BUSH_1))
            elif roll < 0.26:
                items.append(ItemData(id=TerrainTiles.BUSH_2))

        elif biome == Biome.SWAMP:
            if roll < 0.05:
                items.append(ItemData(id=TerrainTiles.BUSH_2))
            elif roll < 0.08:
                fid = rng.randint(TerrainTiles.FLOWER_MIN, TerrainTiles.FLOWER_MAX)
                items.append(ItemData(id=fid))

        elif biome == Biome.JUNGLE:
            if roll < 0.22:
                tid = rng.randint(TerrainTiles.TREE_MIN, TerrainTiles.TREE_MAX)
                items.append(ItemData(id=tid))
            elif roll < 0.28:
                items.append(ItemData(id=TerrainTiles.BUSH_1))
            elif roll < 0.30:
                items.append(ItemData(id=TerrainTiles.BUSH_2))

        return items

    # ---- Public helpers for testing / inspection ----

    def get_biome_map(self) -> List[List[str]]:
        """Generate and return the biome classification grid."""
        elev = self.get_elevation_map()
        biomes: List[List[str]] = []
        for y in range(self.height):
            row: List[str] = []
            for x in range(self.width):
                nx = x * self.biome_scale
                ny = y * self.biome_scale
                m = perlin_2d(nx + 100.0, ny + 100.0,
                              self.seed + self.moisture_seed_offset,
                              octaves=2)
                row.append(classify_biome(elev[y][x], m, self.water_level))
            biomes.append(row)
        return biomes

    def get_elevation_map(self) -> List[List[float]]:
        """Generate and return the elevation grid (with island falloff + normalization)."""
        # First pass: raw values
        raw_elev: List[List[float]] = []
        raw_max = 0.0
        for y in range(self.height):
            row: List[float] = []
            for x in range(self.width):
                nx = x * self.biome_scale
                ny = y * self.biome_scale
                e = perlin_2d(nx, ny, self.seed, octaves=self.octaves)
                e *= self._island_falloff(x, y, self.seed)
                row.append(e)
                raw_max = max(raw_max, e)
            raw_elev.append(row)

        # Normalize
        scale = 0.92 / raw_max if raw_max > 0 else 1.0
        return [[raw_elev[y][x] * scale for x in range(self.width)]
                for y in range(self.height)]
