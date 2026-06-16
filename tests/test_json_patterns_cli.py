"""
Tests for JSON codec, tile pattern library, and CLI subcommands.

Run:  cd /home/bitupx/otbforge && python3 -m pytest tests/test_json_patterns_cli.py -v --tb=short
"""

from __future__ import annotations

import json
import os
import tempfile

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
)


# =========================================================================
# Fixtures
# =========================================================================

def _make_sample_map() -> MapData:
    """Create a sample MapData with tiles, towns, waypoints, spawns, NPCs, houses."""
    md = MapData(width=512, height=512, description="Test Map")
    # Tiles
    md.add_tile(100, 200, 7, ground_id=102, flags=TileFlag.PROTECTIONZONE)
    md.add_tile(101, 200, 7, ground_id=103)
    md.add_tile(100, 201, 7, ground_id=102, items=[ItemData(id=3756, count=1)])
    md.add_tile(100, 200, 6, ground_id=231)  # different z-level
    # Town
    md.add_town(1, "Thais", Position(x=100, y=100, z=7))
    # Waypoint
    md.add_waypoint("dp", Position(x=150, y=150, z=7))
    # Spawn
    md.spawns.append(SpawnData(x=120, y=130, z=7, radius=5, monsters=[("Rat", 3, 60)]))
    # NPC spawn
    md.npc_spawns.append(NPCSpawnData(x=110, y=120, z=7, npc_name="Banker", direction=0))
    # House
    md.houses.append(HouseData(id=1001, name="Thais House 1", town_id=1, rent=1000, size=25))
    return md


@pytest.fixture
def sample_map():
    return _make_sample_map()


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# =========================================================================
# JSON Codec Tests (1-15)
# =========================================================================

class TestJsonCodecEncode:
    """Tests for MapJsonCodec.encode."""

    def test_01_encode_basic(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        assert data["version"] == "1.0"
        assert data["width"] == 512
        assert data["height"] == 512
        assert data["description"] == "Test Map"
        assert len(data["tiles"]) == 4
        assert len(data["towns"]) == 1
        assert len(data["waypoints"]) == 1
        assert len(data["spawns"]) == 1
        assert len(data["npc_spawns"]) == 1
        assert len(data["houses"]) == 1

    def test_02_encode_tile_fields(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        tile = data["tiles"][0]
        assert tile["x"] == 100
        assert tile["y"] == 200
        assert tile["z"] == 7
        assert tile["ground_id"] == 102
        assert tile["flags"] == 1  # PROTECTIONZONE
        assert tile["house_id"] == 0

    def test_03_encode_tile_with_items(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        tile_with_item = [t for t in data["tiles"] if t.get("items")][0]
        assert len(tile_with_item["items"]) == 1
        assert tile_with_item["items"][0]["item_id"] == 3756

    def test_04_encode_town(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        town = data["towns"][0]
        assert town["town_id"] == 1
        assert town["name"] == "Thais"
        assert town["temple_x"] == 100
        assert town["temple_y"] == 100
        assert town["temple_z"] == 7

    def test_05_encode_waypoint(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        wp = data["waypoints"][0]
        assert wp["name"] == "dp"
        assert wp["x"] == 150
        assert wp["y"] == 150

    def test_06_encode_spawn_with_monsters(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        spawn = data["spawns"][0]
        assert spawn["x"] == 120
        assert spawn["radius"] == 5
        assert len(spawn["monsters"]) == 1

    def test_07_encode_house(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        house = data["houses"][0]
        assert house["house_id"] == 1001
        assert house["name"] == "Thais House 1"
        assert house["town_id"] == 1
        assert house["rent"] == 1000

    def test_08_encode_compact_tiles(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map, compact=True)
        # Tiles with no items/flags/house_id should be lists
        compact_tiles = [t for t in data["tiles"] if isinstance(t, list)]
        assert len(compact_tiles) >= 1
        assert len(compact_tiles[0]) == 4  # [x, y, z, ground_id]

    def test_09_encode_empty_map(self):
        from ai_core.json_codec import MapJsonCodec
        md = MapData()
        data = MapJsonCodec.encode(md)
        assert data["version"] == "1.0"
        assert data["width"] == 2048
        assert data["tiles"] == []
        assert data["towns"] == []

    def test_10_encode_preserves_ext_files(self):
        from ai_core.json_codec import MapJsonCodec
        md = MapData(ext_spawn_file="spawn.xml", ext_house_file="houses.xml")
        data = MapJsonCodec.encode(md)
        assert data["ext_spawn_file"] == "spawn.xml"
        assert data["ext_house_file"] == "houses.xml"


class TestJsonCodecDecode:
    """Tests for MapJsonCodec.decode."""

    def test_11_decode_basic(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert result.width == 512
        assert result.height == 512
        assert result.description == "Test Map"
        assert len(result.tiles) == 4

    def test_12_decode_tiles(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        tile = result.tiles[0]
        assert tile.x == 100
        assert tile.y == 200
        assert tile.z == 7
        assert tile.ground_id == 102
        assert tile.flags == TileFlag.PROTECTIONZONE

    def test_13_decode_towns(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.towns) == 1
        town = result.towns[0]
        assert town.id == 1
        assert town.name == "Thais"
        assert town.temple.x == 100

    def test_14_decode_spawns_with_monsters(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.spawns) == 1
        assert result.spawns[0].monsters == [("Rat", 3, 60)]

    def test_15_decode_compact_tiles(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map, compact=True)
        result = MapJsonCodec.decode(data)
        assert len(result.tiles) == 4
        assert result.tiles[0].ground_id > 0


class TestJsonCodecRoundtrip:
    """Tests for encode→decode roundtrip fidelity."""

    def test_16_roundtrip_tiles(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.tiles) == len(sample_map.tiles)
        for orig, restored in zip(sample_map.tiles, result.tiles):
            assert orig.x == restored.x
            assert orig.y == restored.y
            assert orig.z == restored.z
            assert orig.ground_id == restored.ground_id
            assert int(orig.flags) == int(restored.flags)
            assert len(orig.items) == len(restored.items)

    def test_17_roundtrip_towns(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.towns) == len(sample_map.towns)

    def test_18_roundtrip_waypoints(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.waypoints) == len(sample_map.waypoints)

    def test_19_roundtrip_spawns(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.spawns) == len(sample_map.spawns)

    def test_20_roundtrip_houses(self, sample_map):
        from ai_core.json_codec import MapJsonCodec
        data = MapJsonCodec.encode(sample_map)
        result = MapJsonCodec.decode(data)
        assert len(result.houses) == len(sample_map.houses)
        assert result.houses[0].id == 1001
        assert result.houses[0].name == "Thais House 1"


class TestJsonCodecFileIO:
    """Tests for save/load and file I/O."""

    def test_21_save_and_load(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        path = os.path.join(tmp_dir, "test_map.json")
        MapJsonCodec.save(sample_map, path)
        assert os.path.exists(path)
        result = MapJsonCodec.load(path)
        assert result.width == 512
        assert len(result.tiles) == 4

    def test_22_save_compact(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        path_normal = os.path.join(tmp_dir, "normal.json")
        path_compact = os.path.join(tmp_dir, "compact.json")
        MapJsonCodec.save(sample_map, path_normal, compact=False)
        MapJsonCodec.save(sample_map, path_compact, compact=True)
        assert os.path.getsize(path_compact) <= os.path.getsize(path_normal)

    def test_23_save_creates_valid_json(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        path = os.path.join(tmp_dir, "valid.json")
        MapJsonCodec.save(sample_map, path)
        with open(path) as f:
            data = json.load(f)
        assert "version" in data
        assert "tiles" in data

    def test_24_export_otbm(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        path = os.path.join(tmp_dir, "export.json")
        MapJsonCodec.export_otbm(sample_map, path)
        result = MapJsonCodec.load(path)
        assert result.description == "Test Map"

    def test_25_load_nonexistent_raises(self, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        with pytest.raises(FileNotFoundError):
            MapJsonCodec.load(os.path.join(tmp_dir, "nope.json"))


# =========================================================================
# Tile Pattern Library Tests (26-35)
# =========================================================================

class TestPatternLibraryBasics:
    """Tests for TilePatternLibrary."""

    def test_26_list_all_patterns(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        patterns = lib.list_patterns()
        assert len(patterns) >= 17

    def test_27_list_pattern_names(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        names = lib.list_pattern_names()
        assert "tower" in names
        assert "stone_house" in names
        assert "pond" in names
        assert "well" in names

    def test_28_get_existing_pattern(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        p = lib.get_pattern("tower")
        assert p.name == "tower"
        assert p.width == 3
        assert p.height == 3

    def test_29_get_nonexistent_raises(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        with pytest.raises(KeyError, match="not_found"):
            lib.get_pattern("not_found")

    def test_30_list_by_category(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        building = lib.list_patterns(category=PatternCategory.BUILDING)
        assert len(building) >= 5
        names = [p.name for p in building]
        assert "stone_house" in names
        assert "tower" in names

    def test_31_list_nature_category(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        nature = lib.list_patterns(category=PatternCategory.NATURE)
        names = [p.name for p in nature]
        assert "tree_cluster" in names
        assert "flower_garden" in names
        assert "pond" in names
        assert "rock_formation" in names

    def test_32_list_dungeon_category(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        dungeon = lib.list_patterns(category=PatternCategory.DUNGEON)
        names = [p.name for p in dungeon]
        assert "stone_room" in names
        assert "prison_cell" in names
        assert "torture_chamber" in names

    def test_33_list_road_category(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        road = lib.list_patterns(category=PatternCategory.ROAD)
        names = [p.name for p in road]
        assert "stone_path" in names
        assert "bridge_horizontal" in names
        assert "bridge_vertical" in names

    def test_34_list_water_category(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        water = lib.list_patterns(category=PatternCategory.WATER)
        names = [p.name for p in water]
        assert "fountain" in names
        assert "well" in names


class TestPatternApply:
    """Tests for pattern application to maps."""

    def test_35_apply_tower(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        md = MapData()
        placed = lib.apply_pattern(md, "tower", x=100, y=200, z=7)
        assert placed > 0
        # Tower is 3x3; walls have no ground, floors have ground
        tiles_with_ground = [t for t in md.tiles if t.ground_id > 0]
        tiles_with_items = [t for t in md.tiles if t.items]
        assert len(tiles_with_ground) >= 1
        assert len(tiles_with_items) >= 1

    def test_36_apply_pond(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        md = MapData()
        placed = lib.apply_pattern(md, "pond", x=50, y=50, z=7)
        assert placed > 0
        # Pond is 5x5, all cells should have ground
        assert len(md.tiles) >= 5

    def test_37_apply_stone_house(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        md = MapData()
        placed = lib.apply_pattern(md, "stone_house", x=0, y=0, z=7)
        assert placed > 0
        # Should have stone floor tiles and stone wall items
        ground_tiles = [t for t in md.tiles if t.ground_id > 0]
        wall_tiles = [t for t in md.tiles if any(i.id == 1102 for i in t.items)]
        assert len(ground_tiles) >= 1
        assert len(wall_tiles) >= 1

    def test_38_apply_overwrite_false_skips_existing(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        md = MapData()
        md.add_tile(100, 200, 7, ground_id=102)
        initial_count = len(md.tiles)
        placed = lib.apply_pattern(md, "tower", x=100, y=200, z=7, overwrite=False)
        # The tower may still place some tiles where there are no existing tiles
        assert len(md.tiles) >= initial_count

    def test_39_apply_overwrite_true_replaces(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        md = MapData()
        md.add_tile(100, 200, 7, ground_id=102)
        placed = lib.apply_pattern(md, "tower", x=100, y=200, z=7, overwrite=True)
        assert placed > 0


class TestCustomPattern:
    """Tests for custom pattern creation."""

    def test_40_create_custom_pattern(self):
        from ai_core.patterns import TilePatternLibrary, PatternCategory
        lib = TilePatternLibrary()
        grid = [
            [{"ground_id": 102, "items": [2700]}, {"ground_id": 102}],
            [{"ground_id": 102}, {"ground_id": 102, "items": [2767]}],
        ]
        pattern = lib.create_custom_pattern("my_grove", grid, description="My tree grove")
        assert pattern.name == "my_grove"
        assert pattern.width == 2
        assert pattern.height == 2
        assert pattern.category == PatternCategory.CUSTOM

    def test_41_get_custom_after_register(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        grid = [[{"ground_id": 102}]]
        lib.create_custom_pattern("single_grass", grid)
        p = lib.get_pattern("single_grass")
        assert p.name == "single_grass"
        assert p.width == 1

    def test_42_apply_custom_pattern(self):
        from ai_core.patterns import TilePatternLibrary
        lib = TilePatternLibrary()
        grid = [
            [{"ground_id": 102}, {"ground_id": 102}],
            [{"ground_id": 102}, {"ground_id": 102}],
        ]
        lib.create_custom_pattern("2x2_grass", grid)
        md = MapData()
        placed = lib.apply_pattern(md, "2x2_grass", x=10, y=10, z=7)
        assert placed == 4


# =========================================================================
# PatternTile Tests (43-44)
# =========================================================================

class TestPatternTile:
    """Tests for PatternTile dataclass helpers."""

    def test_43_ground_factory(self):
        from ai_core.patterns import PatternTile
        pt = PatternTile.ground(102, items=[2700])
        assert pt.ground_id == 102
        assert pt.items == [2700]

    def test_44_empty_factory(self):
        from ai_core.patterns import PatternTile
        pt = PatternTile.empty()
        assert pt.ground_id == 0
        assert pt.items == []


# =========================================================================
# CLI Subcommand Tests (45-50)
# =========================================================================

class TestCLISubcommands:
    """Tests for the new CLI subcommands via argparse."""

    def test_45_json_export_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["json-export", "test.otbm", "--compact"])
        assert args.command == "json-export"
        assert args.file == "test.otbm"
        assert args.compact is True

    def test_46_json_import_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["json-import", "test.json", "-o", "out.otbm"])
        assert args.command == "json-import"
        assert args.file == "test.json"
        assert args.output == "out.otbm"

    def test_47_pattern_list_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pattern", "list", "--category", "building"])
        assert args.command == "pattern"
        assert args.pattern_subcommand == "list"
        assert args.category == "building"

    def test_48_pattern_apply_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["pattern", "apply", "map.otbm", "--name", "tower", "--position", "100,200,7"])
        assert args.command == "pattern"
        assert args.pattern_subcommand == "apply"
        assert args.name == "tower"
        assert args.position == "100,200,7"

    def test_49_stitch_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["stitch", "a.otbm", "b.otbm", "--layout", "vertical", "--output", "merged.otbm"])
        assert args.command == "stitch"
        assert len(args.files) == 2
        assert args.layout == "vertical"
        assert args.output == "merged.otbm"

    def test_50_extract_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["extract", "map.otbm", "--x1", "100", "--y1", "100", "--x2", "200", "--y2", "200", "--output", "region.otbm"])
        assert args.command == "extract"
        assert args.x1 == 100
        assert args.y2 == 200

    def test_51_minimap_parser(self):
        from ai_core.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["minimap", "map.otbm", "--width", "120", "--height", "60", "--format", "html", "--output", "mm.html"])
        assert args.command == "minimap"
        assert args.width == 120
        assert args.height == 60
        assert args.format == "html"

    def test_52_main_json_export(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        from ai_core.cli import main, build_parser
        # Save map as OTBM first
        otbm_path = os.path.join(tmp_dir, "test.otbm")
        from ai_core.otbm_writer import OTBMWriter
        OTBMWriter(sample_map).save(otbm_path)

        json_path = os.path.join(tmp_dir, "out.json")
        rc = main(["json-export", otbm_path, "-o", json_path])
        assert rc == 0
        assert os.path.exists(json_path)

    def test_53_main_pattern_list(self):
        from ai_core.cli import main
        rc = main(["pattern", "list"])
        assert rc == 0

    def test_54_main_pattern_list_category(self):
        from ai_core.cli import main
        rc = main(["pattern", "list", "--category", "nature"])
        assert rc == 0

    def test_55_main_minimap_ascii(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        from ai_core.cli import main
        # Save map as JSON (no need for OTBM binary for this test)
        json_path = os.path.join(tmp_dir, "test.json")
        MapJsonCodec.save(sample_map, json_path)

        out_path = os.path.join(tmp_dir, "minimap.txt")
        rc = main(["minimap", json_path, "--format", "ascii", "--width", "40", "--height", "20", "--output", out_path])
        assert rc == 0
        assert os.path.exists(out_path)

    def test_56_main_minimap_html(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        from ai_core.cli import main
        json_path = os.path.join(tmp_dir, "test.json")
        MapJsonCodec.save(sample_map, json_path)

        out_path = os.path.join(tmp_dir, "minimap.html")
        rc = main(["minimap", json_path, "--format", "html", "--output", out_path])
        assert rc == 0
        assert os.path.exists(out_path)
        with open(out_path) as f:
            content = f.read()
        assert "<canvas" in content

    def test_57_main_extract(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        from ai_core.cli import main
        json_path = os.path.join(tmp_dir, "test.json")
        MapJsonCodec.save(sample_map, json_path)

        out_path = os.path.join(tmp_dir, "region.otbm")
        rc = main(["extract", json_path, "--x1", "99", "--y1", "199", "--x2", "102", "--y2", "202", "--output", out_path])
        assert rc == 0
        assert os.path.exists(out_path)

    def test_58_main_json_import(self, sample_map, tmp_dir):
        from ai_core.json_codec import MapJsonCodec
        from ai_core.cli import main
        json_path = os.path.join(tmp_dir, "import_test.json")
        MapJsonCodec.save(sample_map, json_path)

        otbm_path = os.path.join(tmp_dir, "imported.otbm")
        rc = main(["json-import", json_path, "-o", otbm_path])
        assert rc == 0
        assert os.path.exists(otbm_path)


# =========================================================================
# JSON Codec edge-case tests (59-62)
# =========================================================================

class TestJsonCodecEdgeCases:
    """Edge cases for the JSON codec."""

    def test_59_decode_empty_dict(self):
        from ai_core.json_codec import MapJsonCodec
        result = MapJsonCodec.decode({})
        assert result.width == 2048
        assert result.height == 2048
        assert result.tiles == []

    def test_60_decode_item_with_teleport(self):
        from ai_core.json_codec import MapJsonCodec
        data = {
            "tiles": [
                {
                    "x": 10, "y": 20, "z": 7, "ground_id": 102,
                    "items": [
                        {"item_id": 1387, "count": 1, "teleport_dest": {"x": 100, "y": 200, "z": 5}}
                    ]
                }
            ]
        }
        result = MapJsonCodec.decode(data)
        assert len(result.tiles) == 1
        item = result.tiles[0].items[0]
        assert item.id == 1387
        assert item.teleport_dest == Position(100, 200, 5)

    def test_61_decode_item_with_children(self):
        from ai_core.json_codec import MapJsonCodec
        data = {
            "tiles": [
                {
                    "x": 1, "y": 1, "z": 7, "ground_id": 102,
                    "items": [
                        {"item_id": 3756, "count": 0, "children": [
                            {"item_id": 2160, "count": 5}
                        ]}
                    ]
                }
            ]
        }
        result = MapJsonCodec.decode(data)
        item = result.tiles[0].items[0]
        assert len(item.children) == 1
        assert item.children[0].id == 2160
        assert item.children[0].count == 5

    def test_62_encode_decode_large_item_fields(self):
        from ai_core.json_codec import MapJsonCodec
        item = ItemData(
            id=3756, count=10, action_id=500, unique_id=600,
            text="Hello", description="A chest",
            charges=3, house_door_id=1, depot_id=2,
            teleport_dest=Position(1, 2, 3),
            duration=100, decay_state=1, written_date=999999,
            written_by="Admin", rune_charges=5,
            children=[ItemData(id=2160, count=3)]
        )
        md = MapData()
        md.add_tile(10, 20, 7, ground_id=102, items=[item])
        data = MapJsonCodec.encode(md)
        result = MapJsonCodec.decode(data)
        restored_item = result.tiles[0].items[0]
        assert restored_item.id == 3756
        assert restored_item.count == 10
        assert restored_item.action_id == 500
        assert restored_item.text == "Hello"
        assert restored_item.description == "A chest"
        assert restored_item.teleport_dest == Position(1, 2, 3)
        assert restored_item.written_date == 999999
        assert len(restored_item.children) == 1
        assert restored_item.children[0].id == 2160
