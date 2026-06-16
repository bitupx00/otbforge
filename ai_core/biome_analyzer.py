"""
Biome Analyzer — Analyze OTBM maps to detect biome composition.

Classifies tiles by ground ID into biome types (grass, dirt, sand, snow,
water, stone, lava, forest, indoor, etc.) and generates reports including
percentage breakdowns, dominant biome, transition zones, and a text-based
heat map of biome distribution.

Usage::

    from ai_core.biome_analyzer import BiomeAnalyzer

    report = BiomeAnalyzer.detect_biomes(map_data)
    print(report.summary())
    print(report.heatmap())

    # From .otbm file
    report = BiomeAnalyzer.from_file("map.otbm")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ai_core.models import (
    MapData,
    TileData,
    Tiles,
)
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Biome types
# ---------------------------------------------------------------------------

class BiomeType(str, Enum):
    """Biome classification types for Tibia tiles."""
    GRASS = "grass"
    FOREST = "forest"        # Trees/bushes/flowers on ground
    DIRT = "dirt"
    SAND = "sand"
    SNOW = "snow"
    WATER = "water"
    STONE = "stone"          # Stone/rock ground
    LAVA = "lava"
    INDOOR = "indoor"        # Wooden floor, carpet, etc.
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Ground ID → biome mappings
# ---------------------------------------------------------------------------

# Well-known Tibia ground IDs and their biome classifications.
# Based on Tibia 8.x client items.
BIOME_GROUND_IDS: Dict[int, BiomeType] = {
    # Grass (102-103 range)
    102: BiomeType.GRASS,
    103: BiomeType.GRASS,
    # More grass variants
    104: BiomeType.GRASS,
    105: BiomeType.GRASS,
    # Dirt (202-203 range)
    202: BiomeType.DIRT,
    203: BiomeType.DIRT,
    204: BiomeType.DIRT,
    # Sand (351-352 range and 231)
    231: BiomeType.SAND,
    351: BiomeType.SAND,
    352: BiomeType.SAND,
    353: BiomeType.SAND,
    # Snow (742, 7731)
    742: BiomeType.SNOW,
    7731: BiomeType.SNOW,
    7732: BiomeType.SNOW,
    # Water (493, 490)
    490: BiomeType.WATER,
    491: BiomeType.WATER,
    492: BiomeType.WATER,
    493: BiomeType.WATER,
    # Stone (563, 3326, 3638, 410-416)
    410: BiomeType.STONE,
    411: BiomeType.STONE,
    412: BiomeType.STONE,
    413: BiomeType.STONE,
    414: BiomeType.STONE,
    415: BiomeType.STONE,
    416: BiomeType.STONE,
    563: BiomeType.STONE,
    3326: BiomeType.STONE,
    3638: BiomeType.STONE,
    1102: BiomeType.STONE,  # stone wall used as ground
    # Lava (884, 5967)
    884: BiomeType.LAVA,
    5967: BiomeType.LAVA,
    5968: BiomeType.LAVA,
    # Indoor (wood floor, carpet)
    530: BiomeType.INDOOR,
    531: BiomeType.INDOOR,
    532: BiomeType.INDOOR,
    5565: BiomeType.INDOOR,
    5566: BiomeType.INDOOR,
    # Forest ground markers (not tile items, but ground that has trees)
    # These are ground IDs that typically appear under trees
    1018: BiomeType.INDOOR,  # wood (wall, but also used as indoor)
    1060: BiomeType.INDOOR,  # brick
}

# Tree/item IDs that indicate forest biome when placed on tiles
FOREST_ITEM_IDS: List[int] = [
    2700, 2701, 2702, 2703, 2704, 2705, 2706, 2707, 2708,  # Trees
    2767, 2768,  # Bushes
    2740, 2741, 2742, 2743,  # Flowers
    3874, 3875,  # More vegetation
]

# Biome display symbols for heat map
BIOME_SYMBOLS: Dict[BiomeType, str] = {
    BiomeType.GRASS: "G",
    BiomeType.FOREST: "F",
    BiomeType.DIRT: "D",
    BiomeType.SAND: "S",
    BiomeType.SNOW: "N",  # 'N' for sNow (S is taken)
    BiomeType.WATER: "W",
    BiomeType.STONE: "R",  # 'R' for Rock
    BiomeType.LAVA: "L",
    BiomeType.INDOOR: "I",
    BiomeType.UNKNOWN: ".",
}


# ---------------------------------------------------------------------------
# Transition zone
# ---------------------------------------------------------------------------

@dataclass
class TransitionZone:
    """Describes a biome transition area."""
    position: Tuple[int, int]  # (x, y) center of transition
    from_biome: BiomeType
    to_biome: BiomeType
    radius: int = 1  # tiles in each direction


# ---------------------------------------------------------------------------
# BiomeReport
# ---------------------------------------------------------------------------

@dataclass
class BiomeReport:
    """Full biome analysis report for a map."""
    total_tiles: int = 0
    analyzed_tiles: int = 0  # tiles with ground_id > 0
    biome_counts: Dict[BiomeType, int] = field(default_factory=dict)
    biome_percentages: Dict[BiomeType, float] = field(default_factory=dict)
    dominant_biome: BiomeType = BiomeType.UNKNOWN
    dominant_percentage: float = 0.0
    transition_zones: List[TransitionZone] = field(default_factory=list)
    ground_id_counts: Dict[int, int] = field(default_factory=dict)
    map_width: int = 0
    map_height: int = 0
    description: str = ""
    _tile_biome_grid: Optional[Dict[Tuple[int, int], "BiomeType"]] = field(
        default=None, repr=False, compare=False
    )

    def summary(self) -> str:
        """Return a text summary of biome analysis."""
        lines = [
            f"Biome Report: {self.description or 'Unknown Map'}",
            f"  Total tiles: {self.total_tiles}",
            f"  Analyzed (ground > 0): {self.analyzed_tiles}",
            f"  Dominant biome: {self.dominant_biome.value} ({self.dominant_percentage:.1f}%)",
            "",
            "  Breakdown:",
        ]
        for biome, pct in sorted(self.biome_percentages.items(), key=lambda x: -x[1]):
            count = self.biome_counts.get(biome, 0)
            bar = "#" * int(pct / 2)  # Simple text bar
            lines.append(f"    {biome.value:>10s}: {pct:6.2f}% ({count:>6d}) {bar}")
        if self.transition_zones:
            lines.append(f"\n  Transition zones: {len(self.transition_zones)}")
        return "\n".join(lines)

    def heatmap(
        self,
        resolution: int = 40,
        cell_size: int = 10,
    ) -> str:
        """Generate a text-based heat map of biome distribution.

        Parameters
        ----------
        resolution : int
            Grid cells per row/column for the heat map.
        cell_size : int
            World units per grid cell.
        """
        if self.analyzed_tiles == 0:
            return "  (no tiles to analyze)"

        # Determine bounds
        # We need to know which cells are populated, so we store tile coordinates
        # in the report for heat map generation. Use ground_id_counts as a proxy
        # for simple heatmap, or use the raw map data.
        # Since BiomeReport doesn't store individual tile positions (to keep memory
        # reasonable), the heatmap is generated from tile_grid passed during creation.
        # We store a reference to the tile grid for heatmap use.
        if not hasattr(self, "_tile_biome_grid") or self._tile_biome_grid is None:
            return "  (heatmap data not available — use BiomeAnalyzer.detect_biomes with store_heatmap=True)"

        grid = self._tile_biome_grid
        if not grid:
            return "  (empty heatmap)"

        lines = []
        lines.append(f"  Biome Heat Map ({resolution}x{resolution})")
        lines.append(f"  Legend: {' '.join(f'{v}={k.value}' for k, v in BIOME_SYMBOLS.items() if k != BiomeType.UNKNOWN)}")
        lines.append("")

        # Calculate world bounds from grid keys
        xs = [k[0] for k in grid.keys()]
        ys = [k[1] for k in grid.keys()]
        if not xs:
            return "  (no tiles)"
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        range_x = max(max_x - min_x, 1)
        range_y = max(max_y - min_y, 1)

        # Sample the grid at resolution x resolution
        for row in range(resolution):
            wy = min_y + (row * range_y) // resolution
            line_parts = []
            for col in range(resolution):
                wx = min_x + (col * range_x) // resolution
                biome = grid.get((wx, wy), BiomeType.UNKNOWN)
                line_parts.append(BIOME_SYMBOLS.get(biome, "."))
            lines.append("  " + "".join(line_parts))

        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Return report as a dictionary."""
        return {
            "total_tiles": self.total_tiles,
            "analyzed_tiles": self.analyzed_tiles,
            "dominant_biome": self.dominant_biome.value,
            "dominant_percentage": round(self.dominant_percentage, 2),
            "biome_percentages": {
                k.value: round(v, 2) for k, v in self.biome_percentages.items()
            },
            "biome_counts": {
                k.value: v for k, v in self.biome_counts.items()
            },
            "transition_zones": len(self.transition_zones),
            "ground_id_counts": self.ground_id_counts,
        }


# ---------------------------------------------------------------------------
# BiomeAnalyzer
# ---------------------------------------------------------------------------

class BiomeAnalyzer:
    """Analyze OTBM maps to detect biome composition.

    Usage::

        report = BiomeAnalyzer.detect_biomes(map_data)
        print(report.summary())

        # From .otbm file
        report = BiomeAnalyzer.from_file("map.otbm")
    """

    @staticmethod
    def detect_biomes(
        map_data: MapData,
        store_heatmap: bool = False,
    ) -> BiomeReport:
        """Analyze a MapData and return a BiomeReport.

        Parameters
        ----------
        map_data : MapData
            The map to analyze.
        store_heatmap : bool
            If True, store per-tile biome data for heatmap generation.
        """
        biome_counts: Dict[BiomeType, int] = {}
        ground_id_counts: Dict[int, int] = {}
        transition_zones: List[TransitionZone] = []
        tile_biome_grid: Dict[Tuple[int, int], BiomeType] = {}

        # Classify each tile
        tile_biomes: List[Tuple[int, int, BiomeType]] = []
        for tile in map_data.tiles:
            if tile.ground_id > 0:
                biome = BiomeAnalyzer._classify_tile(tile)
                biome_counts[biome] = biome_counts.get(biome, 0) + 1
                ground_id_counts[tile.ground_id] = ground_id_counts.get(tile.ground_id, 0) + 1
                tile_biomes.append((tile.x, tile.y, biome))
                if store_heatmap:
                    tile_biome_grid[(tile.x, tile.y)] = biome

        total_tiles = len(map_data.tiles)
        analyzed_tiles = sum(biome_counts.values())

        # Calculate percentages
        biome_percentages: Dict[BiomeType, float] = {}
        dominant_biome = BiomeType.UNKNOWN
        dominant_pct = 0.0

        if analyzed_tiles > 0:
            for biome, count in biome_counts.items():
                pct = (count / analyzed_tiles) * 100.0
                biome_percentages[biome] = pct
                if pct > dominant_pct:
                    dominant_pct = pct
                    dominant_biome = biome

        # Detect transition zones
        if store_heatmap and tile_biomes:
            transition_zones = BiomeAnalyzer._find_transitions(tile_biomes)

        report = BiomeReport(
            total_tiles=total_tiles,
            analyzed_tiles=analyzed_tiles,
            biome_counts=biome_counts,
            biome_percentages=biome_percentages,
            dominant_biome=dominant_biome,
            dominant_percentage=round(dominant_pct, 2),
            transition_zones=transition_zones,
            ground_id_counts=ground_id_counts,
            map_width=map_data.width,
            map_height=map_data.height,
            description=map_data.description,
        )
        # Store grid for heatmap
        report._tile_biome_grid = tile_biome_grid if store_heatmap else None
        return report

    @staticmethod
    def from_file(path: str, store_heatmap: bool = False) -> BiomeReport:
        """Analyze a .otbm file."""
        map_data = OTBMReader.from_file(path)
        return BiomeAnalyzer.detect_biomes(map_data, store_heatmap=store_heatmap)

    @staticmethod
    def from_bytes(data: bytes, store_heatmap: bool = False) -> BiomeReport:
        """Analyze .otbm data from raw bytes."""
        map_data = OTBMReader(data).read()
        return BiomeAnalyzer.detect_biomes(map_data, store_heatmap=store_heatmap)

    @staticmethod
    def classify_ground_id(ground_id: int) -> BiomeType:
        """Classify a single ground ID to its biome type."""
        return BIOME_GROUND_IDS.get(ground_id, BiomeType.UNKNOWN)

    @staticmethod
    def _classify_tile(tile: TileData) -> BiomeType:
        """Classify a tile's biome based on ground ID and items."""
        # Check ground ID first
        biome = BIOME_GROUND_IDS.get(tile.ground_id, BiomeType.UNKNOWN)

        # Check items for forest indicators
        if biome == BiomeType.UNKNOWN or biome == BiomeType.GRASS:
            for item in tile.items:
                if item.id in FOREST_ITEM_IDS:
                    return BiomeType.FOREST

        return biome

    @staticmethod
    def _find_transitions(
        tile_biomes: List[Tuple[int, int, BiomeType]],
    ) -> List[TransitionZone]:
        """Find biome transition zones (adjacent tiles with different biomes)."""
        # Build a position → biome lookup
        biome_map: Dict[Tuple[int, int], BiomeType] = {}
        for x, y, biome in tile_biomes:
            biome_map[(x, y)] = biome

        transitions: List[TransitionZone] = []
        seen: set = set()

        for x, y, biome in tile_biomes:
            for dx, dy in [(1, 0), (0, 1)]:
                neighbor = biome_map.get((x + dx, y + dy))
                if neighbor is not None and neighbor != biome:
                    key = tuple(sorted([(biome, neighbor)]))
                    pos_key = ((x, y), key)
                    if pos_key not in seen:
                        seen.add(pos_key)
                        transitions.append(TransitionZone(
                            position=(x, y),
                            from_biome=biome,
                            to_biome=neighbor,
                            radius=1,
                        ))

        return transitions
