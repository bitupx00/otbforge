"""
Minimap Generator — Produce ASCII, Unicode, and HTML minimaps from OTBM
map data.

The minimap is a downscaled representation of the ground-layer tiles,
colour-coded by biome type (derived from ground IDs).

Usage::

    from ai_core.minimap import MinimapGenerator

    ascii_map = MinimapGenerator.generate_ascii(map_data)
    unicode_map = MinimapGenerator.generate_unicode(map_data)
    html_map = MinimapGenerator.generate_html(map_data, width=400, height=200)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
from ai_core.models import MapData
from ai_core.otbm_reader import OTBMReader


# ---------------------------------------------------------------------------
# Biome → display character / colour mappings
# ---------------------------------------------------------------------------

# ASCII characters (simple single-char)
ASCII_CHARS: Dict[BiomeType, str] = {
    BiomeType.GRASS:   "G",
    BiomeType.FOREST:  "T",
    BiomeType.DIRT:    "D",
    BiomeType.SAND:    "S",
    BiomeType.SNOW:    "N",
    BiomeType.WATER:   "W",
    BiomeType.STONE:   "R",
    BiomeType.LAVA:    "L",
    BiomeType.INDOOR:  "I",
    BiomeType.UNKNOWN: ".",
}

# Unicode block elements (shading progression)
UNICODE_CHARS: Dict[BiomeType, str] = {
    BiomeType.GRASS:   "░",
    BiomeType.FOREST:  "▓",
    BiomeType.DIRT:    "▒",
    BiomeType.SAND:    "░",
    BiomeType.SNOW:   "█",
    BiomeType.WATER:   "▒",
    BiomeType.STONE:   "▓",
    BiomeType.LAVA:    "█",
    BiomeType.INDOOR:  "░",
    BiomeType.UNKNOWN: " ",
}

# HTML hex colours per biome
HTML_COLORS: Dict[BiomeType, str] = {
    BiomeType.GRASS:   "#4CAF50",   # green
    BiomeType.FOREST:  "#2E7D32",   # dark green
    BiomeType.DIRT:    "#8D6E63",   # brown
    BiomeType.SAND:    "#F9A825",   # yellow
    BiomeType.SNOW:    "#FAFAFA",   # white
    BiomeType.WATER:   "#1565C0",   # blue
    BiomeType.STONE:   "#757575",   # gray
    BiomeType.LAVA:    "#D32F2F",   # red
    BiomeType.INDOOR:  "#6D4C41",   # brown
    BiomeType.UNKNOWN: "#212121",   # near-black
}


# ---------------------------------------------------------------------------
# Downsample helper
# ---------------------------------------------------------------------------

def _downsample(
    tile_biome_grid: Dict[Tuple[int, int], BiomeType],
    target_w: int,
    target_h: int,
    map_width: int,
    map_height: int,
) -> List[List[BiomeType]]:
    """Downsample the per-tile biome grid to *target_w* × *target_h*.

    Each output cell covers a rectangular area of the source.  The most
    common biome in each cell wins (majority vote).  If the cell is empty
    the result is ``UNKNOWN``.
    """
    if map_width <= 0 or map_height <= 0:
        return [[BiomeType.UNKNOWN] * target_w for _ in range(target_h)]

    cell_w = map_width / target_w
    cell_h = map_height / target_h

    grid: List[List[BiomeType]] = []
    for row in range(target_h):
        line: List[BiomeType] = []
        y_start = int(row * cell_h)
        y_end = int((row + 1) * cell_h)
        for col in range(target_w):
            x_start = int(col * cell_w)
            x_end = int((col + 1) * cell_w)

            # Majority vote
            counts: Dict[BiomeType, int] = {}
            for x in range(x_start, x_end):
                for y in range(y_start, y_end):
                    b = tile_biome_grid.get((x, y), BiomeType.UNKNOWN)
                    counts[b] = counts.get(b, 0) + 1

            # Filter out UNKNOWN — only count real biomes
            real = {b: c for b, c in counts.items() if b != BiomeType.UNKNOWN}
            if real:
                best = max(real, key=lambda k: real[k])
            else:
                best = BiomeType.UNKNOWN
            line.append(best)
        grid.append(line)
    return grid


# ---------------------------------------------------------------------------
# MinimapGenerator
# ---------------------------------------------------------------------------

class MinimapGenerator:
    """Generate visual minimaps from :class:`MapData` maps."""

    @staticmethod
    def generate_ascii(
        map_data: MapData,
        width: int = 80,
        height: int = 40,
    ) -> str:
        """Return an ASCII-art minimap string.

        Parameters
        ----------
        map_data : MapData
            Source map.
        width, height : int
            Output columns / rows (characters).
        """
        grid = MinimapGenerator._build_biome_grid(map_data)
        sampled = _downsample(grid, width, height, map_data.width, map_data.height)
        lines: List[str] = []
        for row in sampled:
            lines.append("".join(ASCII_CHARS.get(b, ".") for b in row))
        return "\n".join(lines)

    @staticmethod
    def generate_unicode(
        map_data: MapData,
        width: int = 80,
        height: int = 40,
    ) -> str:
        """Return a Unicode minimap string using block-element characters.

        Parameters
        ----------
        map_data : MapData
            Source map.
        width, height : int
            Output columns / rows (characters).
        """
        grid = MinimapGenerator._build_biome_grid(map_data)
        sampled = _downsample(grid, width, height, map_data.width, map_data.height)
        lines: List[str] = []
        for row in sampled:
            lines.append("".join(UNICODE_CHARS.get(b, " ") for b in row))
        return "\n".join(lines)

    @staticmethod
    def generate_html(
        map_data: MapData,
        width: int = 400,
        height: int = 200,
    ) -> str:
        """Return an HTML string with an inline ``<canvas>`` minimap.

        The canvas is drawn pixel-by-pixel using JavaScript embedded in
        the HTML.  Each pixel is coloured according to the dominant biome
        in the corresponding source region.

        Parameters
        ----------
        map_data : MapData
            Source map.
        width, height : int
            Canvas pixel dimensions.
        """
        grid = MinimapGenerator._build_biome_grid(map_data)
        sampled = _downsample(grid, width, height, map_data.width, map_data.height)

        # Build a JS array of hex colours
        colour_rows: List[str] = []
        for row in sampled:
            colour_rows.append(
                "[" + ",".join(HTML_COLORS.get(b, HTML_COLORS[BiomeType.UNKNOWN]) for b in row) + "]"
            )
        colour_data = ",\n".join(colour_rows)

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Minimap</title></head>
<body style="margin:0;background:#111;display:flex;justify-content:center;align-items:center;min-height:100vh;">
<canvas id="mm" width="{width}" height="{height}" style="image-rendering:pixelated;"></canvas>
<script>
(function() {{
  var data = [{colour_data}];
  var c = document.getElementById('mm');
  var ctx = c.getContext('2d');
  for (var y = 0; y < {height}; y++) {{
    for (var x = 0; x < {width}; x++) {{
      ctx.fillStyle = data[y][x];
      ctx.fillRect(x, y, 1, 1);
    }}
  }}
}})();
</script>
</body>
</html>"""
        return html

    @staticmethod
    def generate_ascii_file(path: str, width: int = 80, height: int = 40) -> str:
        """Generate ASCII minimap directly from an ``.otbm`` file."""
        map_data = OTBMReader.from_file(path)
        return MinimapGenerator.generate_ascii(map_data, width=width, height=height)

    @staticmethod
    def generate_html_file(path: str, width: int = 400, height: int = 200) -> str:
        """Generate HTML minimap directly from an ``.otbm`` file."""
        map_data = OTBMReader.from_file(path)
        return MinimapGenerator.generate_html(map_data, width=width, height=height)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_biome_grid(map_data: MapData) -> Dict[Tuple[int, int], BiomeType]:
        """Build a sparse grid of biome types from map tiles (z=0 only, or
        highest-populated z if z=0 has no tiles)."""
        # Prefer z=0 for the minimap, but fall back to whatever has tiles
        z_targets = {0}
        if not any(t.z == 0 and t.ground_id > 0 for t in map_data.tiles):
            if map_data.tiles:
                z_targets = {min(t.z for t in map_data.tiles if t.ground_id > 0)}

        grid: Dict[Tuple[int, int], BiomeType] = {}
        for tile in map_data.tiles:
            if tile.z not in z_targets:
                continue
            if tile.ground_id <= 0:
                continue
            biome = BiomeAnalyzer.classify_ground_id(tile.ground_id)
            # Check items for forest override
            if biome in (BiomeType.UNKNOWN, BiomeType.GRASS):
                for item in tile.items:
                    if item.id in (2700, 2701, 2702, 2703, 2704, 2705, 2706, 2707, 2708,
                                   2767, 2768, 2740, 2741, 2742, 2743, 3874, 3875):
                        biome = BiomeType.FOREST
                        break
            grid[(tile.x, tile.y)] = biome
        return grid
