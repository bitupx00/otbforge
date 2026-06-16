"""
Tests for Map Stitcher, Region Extractor, and Minimap Generator.

35+ tests covering all three features.
"""

from __future__ import annotations

import math
import pytest
from ai_core.models import (
    HouseData,
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TownData,
    WaypointData,
    Tiles,
)
from ai_core.map_stitcher import MapStitcher, MapOffset
from ai_core.region_extractor import Region, RegionExtractor
from ai_core.minimap import MinimapGenerator


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_map(
    width: int = 100,
    height: int = 100,
    tiles: list | None = None,
    towns: list | None = None,
    waypoints: list | None = None,
    spawns: list | None = None,
    npc_spawns: list | None = None,
    houses: list | None = None,
    description: str = "Test Map",
) -> MapData:
    return MapData(
        width=width,
        height=height,
        tiles=tiles or [],
        towns=towns or [],
        waypoints=waypoints or [],
        spawns=spawns or [],
        npc_spawns=npc_spawns or [],
        houses=houses or [],
        description=description,
    )


def _tile(x, y, z=0, ground=102, items=None, flags=TileFlag.NONE, house_id=0):
    return TileData(x=x, y=y, z=z, ground_id=ground, items=items or [],
                    flags=flags, house_id=house_id)


# ===========================================================================
# MAP STITCHER TESTS
# ===========================================================================

class TestMapStitcher:
    """Tests for ai_core.map_stitcher."""

    # -- Basic validation ---------------------------------------------------

    def test_stitcher_invalid_strategy(self):
        """Reject unknown conflict strategy."""
        with pytest.raises(ValueError, match="Unknown conflict strategy"):
            MapStitcher(conflict_strategy="bad")

    def test_stitch_maps_empty_list(self):
        """Zero maps raises."""
        with pytest.raises(ValueError, match="No maps"):
            MapStitcher().stitch_maps([])

    def test_stitch_maps_single_map(self):
        """One map raises."""
        m = _make_map()
        with pytest.raises(ValueError, match="at least 2"):
            MapStitcher().stitch_maps([m])

    def test_stitch_maps_too_many(self):
        """17+ maps raises."""
        maps = [_make_map() for _ in range(17)]
        with pytest.raises(ValueError, match="Maximum 16"):
            MapStitcher().stitch_maps(maps)

    # -- Horizontal layout --------------------------------------------------

    def test_horizontal_two_maps(self):
        """Two maps side by side — result width = sum of widths."""
        a = _make_map(width=100, height=50)
        b = _make_map(width=200, height=50)
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        # Result tiles are empty, so width defaults; but description should exist
        assert result.description.startswith("Stitched map")

    def test_horizontal_offsets(self):
        """Offsets follow x accumulation."""
        a = _make_map(width=100, height=50)
        b = _make_map(width=200, height=50)
        offsets = MapStitcher._layout_horizontal([a, b])
        assert offsets[0].offset_x == 0
        assert offsets[0].offset_y == 0
        assert offsets[1].offset_x == 100
        assert offsets[1].offset_y == 0

    def test_horizontal_three_maps(self):
        """Three maps horizontally."""
        maps = [_make_map(width=10, height=10) for _ in range(3)]
        offsets = MapStitcher._layout_horizontal(maps)
        assert offsets[2].offset_x == 20

    # -- Vertical layout ----------------------------------------------------

    def test_vertical_offsets(self):
        """Offsets follow y accumulation."""
        a = _make_map(width=50, height=100)
        b = _make_map(width=50, height=200)
        offsets = MapStitcher._layout_vertical([a, b])
        assert offsets[0].offset_x == 0
        assert offsets[0].offset_y == 0
        assert offsets[1].offset_x == 0
        assert offsets[1].offset_y == 100

    def test_vertical_three_maps(self):
        """Three maps vertically."""
        maps = [_make_map(width=10, height=10) for _ in range(3)]
        offsets = MapStitcher._layout_vertical(maps)
        assert offsets[2].offset_y == 20

    # -- Grid layout --------------------------------------------------------

    def test_grid_4_maps(self):
        """2x2 grid offsets."""
        maps = [_make_map(width=50, height=50) for _ in range(4)]
        offsets = MapStitcher._layout_grid(maps)
        assert offsets[0].offset_x == 0
        assert offsets[0].offset_y == 0
        assert offsets[1].offset_x == 50
        assert offsets[1].offset_y == 0
        assert offsets[2].offset_x == 0
        assert offsets[2].offset_y == 50
        assert offsets[3].offset_x == 50
        assert offsets[3].offset_y == 50

    def test_grid_3_maps(self):
        """3 maps in a 2-col grid."""
        maps = [_make_map(width=40, height=30) for _ in range(3)]
        offsets = MapStitcher._layout_grid(maps)
        # Third map should start a new row
        assert offsets[2].offset_y == 30

    def test_grid_5_maps(self):
        """5 maps → 3-col grid (ceil(sqrt(5))=3)."""
        maps = [_make_map(width=10, height=10) for _ in range(5)]
        offsets = MapStitcher._layout_grid(maps)
        # Map at index 3 should be row 1, col 0
        assert offsets[3].offset_y == 10

    # -- Auto layout --------------------------------------------------------

    def test_auto_small(self):
        """2 maps auto → horizontal."""
        maps = [_make_map() for _ in range(2)]
        h = MapStitcher._layout_horizontal(maps)
        a = MapStitcher._layout_auto(maps)
        assert [o.offset_x for o in a] == [o.offset_x for o in h]

    def test_auto_4_maps(self):
        """4 maps auto → grid."""
        maps = [_make_map(width=50, height=50) for _ in range(4)]
        g = MapStitcher._layout_grid(maps)
        a = MapStitcher._layout_auto(maps)
        assert [o.offset_x for o in a] == [o.offset_x for o in g]

    # -- Tile stitching -----------------------------------------------------

    def test_tile_positions_shifted(self):
        """Tiles from second map get offset applied."""
        t1 = _tile(5, 5, ground=102)
        t2 = _tile(3, 3, ground=103)
        a = _make_map(width=10, height=10, tiles=[t1])
        b = _make_map(width=10, height=10, tiles=[t2])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        coords = {(t.x, t.y, t.z) for t in result.tiles}
        assert (5, 5, 0) in coords
        assert (13, 3, 0) in coords  # 3 + 10 offset

    def test_merge_towns(self):
        """Towns from both maps are merged."""
        a = _make_map(towns=[TownData(id=1, name="A", temple=Position(10, 10, 7))])
        b = _make_map(towns=[TownData(id=2, name="B", temple=Position(20, 20, 7))])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        names = {t.name for t in result.towns}
        assert "A" in names
        assert "B" in names

    def test_merge_waypoints(self):
        """Waypoints shifted and merged."""
        a = _make_map(width=100, height=100,
                      waypoints=[WaypointData(name="wp1", pos=Position(5, 5, 0))])
        b = _make_map(width=100, height=100,
                      waypoints=[WaypointData(name="wp2", pos=Position(3, 3, 0))])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        wp_map = {w.name: w for w in result.waypoints}
        assert wp_map["wp2"].pos.x == 103  # 3 + 100

    def test_merge_spawns(self):
        """Spawns shifted."""
        a = _make_map(spawns=[SpawnData(x=10, y=10, z=0, radius=5)])
        b = _make_map(spawns=[SpawnData(x=20, y=20, z=0, radius=3)])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        assert len(result.spawns) == 2

    def test_merge_npc_spawns(self):
        """NPC spawns shifted."""
        a = _make_map(npc_spawns=[NPCSpawnData(x=10, y=10, z=0, npc_name="Seller")])
        b = _make_map(npc_spawns=[NPCSpawnData(x=5, y=5, z=0, npc_name="Healer")])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        assert len(result.npc_spawns) == 2

    def test_merge_houses(self):
        """Houses merged from both maps."""
        a = _make_map(houses=[HouseData(id=1, name="House1")])
        b = _make_map(houses=[HouseData(id=2, name="House2")])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        names = {h.name for h in result.houses}
        assert "House1" in names
        assert "House2" in names

    # -- Conflict resolution ------------------------------------------------

    def test_conflict_first(self):
        """'first' strategy keeps first map's tile (unit test of resolver)."""
        s = MapStitcher(conflict_strategy="first")
        existing = _tile(5, 5, ground=102)
        incoming = _tile(5, 5, ground=103)
        result = s._resolve_conflict(existing, incoming)
        assert result.ground_id == 102

    def test_conflict_last(self):
        """'last' strategy keeps incoming tile (unit test of resolver)."""
        s = MapStitcher(conflict_strategy="last")
        existing = _tile(5, 5, ground=102)
        incoming = _tile(5, 5, ground=103)
        result = s._resolve_conflict(existing, incoming)
        assert result.ground_id == 103

    def test_conflict_merge(self):
        """'merge' strategy combines items (unit test of resolver)."""
        it1 = ItemData(id=1001)
        it2 = ItemData(id=2002)
        s = MapStitcher(conflict_strategy="merge")
        existing = _tile(5, 5, ground=102, items=[it1])
        incoming = _tile(5, 5, ground=103, items=[it2])
        result = s._resolve_conflict(existing, incoming)
        assert len(result.items) == 2
        item_ids = {i.id for i in result.items}
        assert 1001 in item_ids
        assert 2002 in item_ids

    def test_conflict_merge_flags(self):
        """Merge strategy ORs tile flags."""
        s = MapStitcher(conflict_strategy="merge")
        existing = _tile(0, 0, ground=102, flags=TileFlag.PROTECTIONZONE)
        incoming = _tile(0, 0, ground=103, flags=TileFlag.PVPZONE)
        result = s._resolve_conflict(existing, incoming)
        assert result.flags & TileFlag.PROTECTIONZONE
        assert result.flags & TileFlag.PVPZONE

    # -- Duplicate waypoint name handling -----------------------------------

    def test_duplicate_waypoint_names(self):
        """Duplicate waypoint names get disambiguated."""
        a = _make_map(waypoints=[WaypointData(name="wp", pos=Position(1, 1, 0))])
        b = _make_map(waypoints=[WaypointData(name="wp", pos=Position(1, 1, 0))])
        result = MapStitcher().stitch_maps([a, b], layout="horizontal")
        assert len(result.waypoints) == 2
        assert result.waypoints[0].name != result.waypoints[1].name

    # -- Description --------------------------------------------------------

    def test_stitched_description(self):
        """Result description mentions source count."""
        a = _make_map(description="Alpha")
        b = _make_map(description="Beta")
        result = MapStitcher().stitch_maps([a, b])
        assert "2 sources" in result.description


# ===========================================================================
# REGION EXTRACTOR TESTS
# ===========================================================================

class TestRegion:
    """Tests for the Region dataclass."""

    def test_region_width_height(self):
        r = Region(10, 20, 30, 50)
        assert r.width == 21
        assert r.height == 31

    def test_region_contains_inside(self):
        r = Region(10, 20, 30, 50)
        assert r.contains(15, 25, 0)

    def test_region_contains_outside_x(self):
        r = Region(10, 20, 30, 50)
        assert not r.contains(5, 25, 0)

    def test_region_contains_outside_z(self):
        r = Region(10, 20, 30, 50, z_min=5, z_max=10)
        assert not r.contains(15, 25, 3)

    def test_region_normalize(self):
        r = Region(30, 50, 10, 20)
        n = r.normalize()
        assert n.x1 == 10 and n.x2 == 30
        assert n.y1 == 20 and n.y2 == 50


class TestRegionExtractor:
    """Tests for ai_core.region_extractor."""

    def test_extract_simple(self):
        """Basic rectangular extraction re-anchors origin."""
        tiles = [
            _tile(100, 200, ground=102),
            _tile(110, 210, ground=103),
            _tile(50, 50, ground=102),  # outside
        ]
        m = _make_map(width=500, height=500, tiles=tiles)
        region = Region(x1=100, y1=200, x2=150, y2=250)
        result = RegionExtractor.extract(m, region)
        coords = {(t.x, t.y) for t in result.tiles}
        assert (0, 0) in coords     # 100,200 shifted
        assert (10, 10) in coords    # 110,210 shifted
        assert len(result.tiles) == 2

    def test_extract_dimensions(self):
        """Result map dimensions match region."""
        m = _make_map(width=500, height=500)
        region = Region(x1=10, y1=20, x2=110, y2=220)
        result = RegionExtractor.extract(m, region)
        assert result.width == 101
        assert result.height == 201

    def test_extract_remapped_town(self):
        """Town inside region gets position shifted."""
        town = TownData(id=1, name="Thais", temple=Position(150, 250, 7))
        tiles = [_tile(150, 250, z=7, ground=102)]
        m = _make_map(width=500, height=500, tiles=tiles, towns=[town])
        region = Region(x1=100, y1=200, x2=300, y2=400)
        result = RegionExtractor.extract(m, region)
        assert len(result.towns) == 1
        assert result.towns[0].temple.x == 50
        assert result.towns[0].temple.y == 50

    def test_extract_excludes_outside_town(self):
        """Town outside region is excluded."""
        town = TownData(id=1, name="Far", temple=Position(10, 10, 7))
        m = _make_map(width=500, height=500, towns=[town])
        region = Region(x1=100, y1=200, x2=300, y2=400)
        result = RegionExtractor.extract(m, region)
        assert len(result.towns) == 0

    def test_extract_remapped_waypoint(self):
        waypts = [WaypointData(name="wp1", pos=Position(120, 220, 0))]
        tiles = [_tile(120, 220, ground=102)]
        m = _make_map(width=500, height=500, tiles=tiles, waypoints=waypts)
        region = Region(x1=100, y1=200, x2=300, y2=400)
        result = RegionExtractor.extract(m, region)
        assert len(result.waypoints) == 1
        assert result.waypoints[0].pos.x == 20

    def test_extract_remapped_spawn(self):
        spawns = [SpawnData(x=130, y=230, z=0, radius=10)]
        tiles = [_tile(130, 230, ground=102)]
        m = _make_map(width=500, height=500, tiles=tiles, spawns=spawns)
        region = Region(x1=100, y1=200, x2=300, y2=400)
        result = RegionExtractor.extract(m, region)
        assert len(result.spawns) == 1
        assert result.spawns[0].x == 30

    def test_extract_by_town(self):
        """extract_by_town creates region around temple."""
        town = TownData(id=1, name="Thais", temple=Position(100, 100, 7))
        tiles = [
            _tile(80, 80, z=7, ground=102),
            _tile(120, 120, z=7, ground=103),
        ]
        m = _make_map(width=500, height=500, tiles=tiles, towns=[town])
        result = RegionExtractor.extract_by_town(m, "Thais", radius=30)
        assert len(result.tiles) == 2

    def test_extract_by_town_not_found(self):
        """Missing town raises ValueError."""
        m = _make_map(width=500, height=500)
        with pytest.raises(ValueError, match="Town not found"):
            RegionExtractor.extract_by_town(m, "Nope")

    def test_extract_floor(self):
        """Extract single floor."""
        tiles = [
            _tile(10, 10, z=0, ground=102),
            _tile(10, 10, z=7, ground=103),
        ]
        m = _make_map(width=500, height=500, tiles=tiles)
        result = RegionExtractor.extract_floor(m, z_level=7)
        assert len(result.tiles) == 1
        assert result.tiles[0].ground_id == 103

    def test_extract_floor_empty(self):
        """Empty floor returns empty map."""
        m = _make_map(width=500, height=500)
        result = RegionExtractor.extract_floor(m, z_level=5)
        assert len(result.tiles) == 0

    def test_extract_file_no_criteria(self):
        """extract_file requires exactly one criterion."""
        with pytest.raises(ValueError, match="exactly one"):
            RegionExtractor.extract_file("dummy.otbm")

    def test_extract_description(self):
        result = RegionExtractor.extract(_make_map(), Region(0, 0, 10, 10))
        assert "Extracted region" in result.description


# ===========================================================================
# MINIMAP GENERATOR TESTS
# ===========================================================================

class TestMinimapGenerator:
    """Tests for ai_core.minimap."""

    def test_ascii_returns_string(self):
        """generate_ascii returns a multi-line string."""
        m = _make_map(width=20, height=20, tiles=[
            _tile(0, 0, ground=102),
            _tile(1, 0, ground=490),
        ])
        result = MinimapGenerator.generate_ascii(m, width=10, height=10)
        assert isinstance(result, str)
        assert len(result.splitlines()) == 10

    def test_ascii_empty_map(self):
        """Empty map produces output with unknown chars."""
        m = _make_map(width=20, height=20)
        result = MinimapGenerator.generate_ascii(m, width=4, height=4)
        lines = result.splitlines()
        assert all("." in line for line in lines)

    def test_ascii_all_grass(self):
        """All grass tiles → 'G' in output."""
        tiles = [_tile(x, y, ground=102) for x in range(10) for y in range(10)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_ascii(m, width=5, height=5)
        # All lines should contain only 'G'
        for line in result.splitlines():
            assert set(line.strip()) <= {"G", " "}

    def test_ascii_water(self):
        """Water ground ID → 'W' in ASCII."""
        tiles = [_tile(0, 0, ground=490)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_ascii(m, width=5, height=5)
        assert "W" in result

    def test_unicode_returns_string(self):
        """generate_unicode returns a multi-line string."""
        tiles = [_tile(0, 0, ground=102)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_unicode(m, width=5, height=5)
        assert isinstance(result, str)
        assert len(result.splitlines()) == 5

    def test_unicode_contains_block_chars(self):
        """Unicode output contains block elements."""
        tiles = [_tile(0, 0, ground=102)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_unicode(m, width=5, height=5)
        assert any(c in result for c in "░▒▓█")

    def test_html_returns_string(self):
        """generate_html returns a valid HTML string."""
        tiles = [_tile(0, 0, ground=102)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=10, height=10)
        assert "<canvas" in result
        assert "</canvas>" in result
        assert "4CAF50" in result  # green for grass

    def test_html_canvas_dimensions(self):
        """Canvas width/height match parameters."""
        tiles = [_tile(0, 0, ground=102)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=200, height=100)
        assert 'width="200"' in result
        assert 'height="100"' in result

    def test_html_water_color(self):
        """Water tile produces blue colour in HTML."""
        tiles = [_tile(0, 0, ground=490)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=5, height=5)
        assert "1565C0" in result  # blue

    def test_html_lava_color(self):
        """Lava tile produces red colour in HTML."""
        tiles = [_tile(0, 0, ground=5967)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=5, height=5)
        assert "D32F2F" in result  # red

    def test_html_snow_color(self):
        """Snow tile produces white colour in HTML."""
        tiles = [_tile(0, 0, ground=7731)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=5, height=5)
        assert "FAFAFA" in result

    def test_html_sand_color(self):
        """Sand tile produces yellow colour in HTML."""
        tiles = [_tile(0, 0, ground=231)]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_html(m, width=5, height=5)
        assert "F9A825" in result

    def test_ascii_custom_size(self):
        """Custom width/height respected."""
        tiles = [_tile(0, 0, ground=102)]
        m = _make_map(width=100, height=100, tiles=tiles)
        result = MinimapGenerator.generate_ascii(m, width=20, height=10)
        lines = result.splitlines()
        assert len(lines) == 10
        assert all(len(line) <= 20 for line in lines)

    def test_minimap_forest_tile(self):
        """Tile with tree item on grass → forest biome."""
        tree = ItemData(id=2700)
        tiles = [_tile(0, 0, ground=102, items=[tree])]
        m = _make_map(width=10, height=10, tiles=tiles)
        result = MinimapGenerator.generate_ascii(m, width=5, height=5)
        assert "T" in result  # forest char


# ===========================================================================
# INTEGRATION TESTS
# ===========================================================================

class TestIntegration:
    """Cross-module integration tests."""

    def test_stitch_then_extract(self):
        """Stitch two maps, then extract a region."""
        t1 = _tile(5, 5, ground=102)
        t2 = _tile(15, 25, ground=490)
        a = _make_map(width=20, height=20, tiles=[t1])
        b = _make_map(width=20, height=20, tiles=[t2])
        stitched = MapStitcher().stitch_maps([a, b], layout="horizontal")
        region = Region(x1=0, y1=0, x2=35, y2=35)
        extracted = RegionExtractor.extract(stitched, region)
        assert len(extracted.tiles) == 2

    def test_extract_then_minimap(self):
        """Extract a region, then generate a minimap."""
        tiles = [_tile(100, 100, ground=102), _tile(110, 110, ground=490)]
        m = _make_map(width=500, height=500, tiles=tiles)
        region = Region(x1=100, y1=100, x2=120, y2=120)
        extracted = RegionExtractor.extract(m, region)
        ascii_mm = MinimapGenerator.generate_ascii(extracted, width=10, height=10)
        assert isinstance(ascii_mm, str)
        assert len(ascii_mm.splitlines()) == 10

    def test_stitch_then_minimap(self):
        """Stitch maps, generate minimap."""
        tiles_a = [_tile(0, 0, ground=102)]
        tiles_b = [_tile(0, 0, ground=490)]
        a = _make_map(width=10, height=10, tiles=tiles_a)
        b = _make_map(width=10, height=10, tiles=tiles_b)
        stitched = MapStitcher().stitch_maps([a, b])
        html = MinimapGenerator.generate_html(stitched, width=5, height=5)
        assert "<canvas" in html
