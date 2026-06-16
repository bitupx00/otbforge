"""Terrain generator using 2D Perlin-like noise (from scratch, no external deps)."""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    Position,
    TileData,
    Tiles,
)


# ---------------------------------------------------------------------------
# Perlin-like value-noise implementation
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
# Biome helpers
# ---------------------------------------------------------------------------

def _distance_to_edge(x: int, y: int, w: int, h: int) -> float:
    """Normalised distance to the nearest map edge [0, 1]. 0 = centre."""
    cx, cy = w / 2, h / 2
    dx = abs(x - cx) / cx
    dy = abs(y - cy) / cy
    return max(dx, dy)


@dataclass
class TerrainGenerator:
    width: int = 256
    height: int = 256
    seed: int = 42
    water_level: float = 0.38
    biome_scale: float = 0.02
    octaves: int = 4
    rivers: bool = False

    def generate(self) -> MapData:
        rng = random.Random(self.seed)
        tiles: List[TileData] = []

        # Pre-compute elevation & moisture grids
        elev = [[0.0] * self.width for _ in range(self.height)]
        moist = [[0.0] * self.width for _ in range(self.height)]

        for y in range(self.height):
            for x in range(self.width):
                nx = x * self.biome_scale
                ny = y * self.biome_scale
                e = perlin_2d(nx, ny, self.seed, octaves=self.octaves)
                # Island mask: lower near edges
                edge_dist = _distance_to_edge(x, y, self.width, self.height)
                edge_factor = max(0.0, 1.0 - edge_dist * edge_dist * 1.2)
                e *= edge_factor
                elev[y][x] = e
                moist[y][x] = perlin_2d(nx + 100.0, ny + 100.0, self.seed + 1,
                                         octaves=2)

        # Optional rivers
        river_cells: set = set()
        if self.rivers:
            river_cells = self._carve_rivers(elev, rng)

        # Generate tiles
        for y in range(self.height):
            for x in range(self.width):
                e = elev[y][x]
                m = moist[y][x]

                if (x, y) in river_cells:
                    ground = Tiles.WATER
                elif e < self.water_level:
                    ground = Tiles.WATER
                elif e < self.water_level + 0.04:
                    ground = Tiles.SAND
                elif e > 0.82:
                    ground = Tiles.SNOW
                elif e > 0.65:
                    ground = Tiles.ROCK
                elif m > 0.55:
                    ground = Tiles.GRASS  # forest floor (trees added as items)
                else:
                    ground = Tiles.GRASS if m > 0.3 else Tiles.DIRT

                items: List[ItemData] = []

                # Vegetation
                if ground == Tiles.GRASS:
                    r = rng.random()
                    if e > 0.55 and m > 0.55 and r < 0.12:
                        tid = rng.randint(Tiles.TREE_MIN, Tiles.TREE_MAX)
                        items.append(ItemData(id=tid))
                    elif r < 0.04:
                        fid = rng.randint(Tiles.FLOWER_MIN, Tiles.FLOWER_MAX)
                        items.append(ItemData(id=fid))
                    elif r < 0.06:
                        items.append(ItemData(id=Tiles.BUSH_1))
                elif ground == Tiles.DIRT and rng.random() < 0.02:
                    items.append(ItemData(id=Tiles.BUSH_2))

                tiles.append(TileData(x=x, y=y, z=0, ground_id=ground, items=items))

        return MapData(
            width=self.width,
            height=self.height,
            description=f"Terrain seed={self.seed}",
            tiles=tiles,
        )

    # ---- River carving (simple path from high→low) ----

    def _carve_rivers(self, elev: List[List[float]],
                      rng: random.Random) -> set:
        cells: set = set()
        w, h = self.width, self.height

        # Find a few high points near center to start rivers
        starts: List[Tuple[int, int]] = []
        for _ in range(rng.randint(2, 5)):
            sx = rng.randint(w // 4, 3 * w // 4)
            sy = rng.randint(h // 4, 3 * h // 4)
            if elev[sy][sx] > 0.6:
                starts.append((sx, sy))

        for sx, sy in starts:
            cx, cy = sx, sy
            visited = set()
            for _ in range(max(w, h)):
                if cx < 0 or cx >= w or cy < 0 or cy >= h:
                    break
                if elev[cy][cx] < self.water_level:
                    break
                if (cx, cy) in visited:
                    break
                visited.add((cx, cy))
                # Carve 1-2 wide
                cells.add((cx, cy))
                if 0 <= cx + 1 < w:
                    cells.add((cx + 1, cy))
                # Move towards lowest neighbor
                best, bx, by = float("inf"), cx, cy
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                               (-1, -1), (1, -1), (-1, 1), (1, 1)):
                    nx2, ny2 = cx + dx, cy + dy
                    if 0 <= nx2 < w and 0 <= ny2 < h:
                        if elev[ny2][nx2] < best:
                            best = elev[ny2][nx2]
                            bx, by = nx2, ny2
                cx, cy = bx, by

        return cells
