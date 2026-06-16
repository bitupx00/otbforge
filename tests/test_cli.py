"""Tests for OTBForge CLI: generate, validate, info, convert subcommands."""

import json
import os
import pytest
import sys
from io import StringIO

from ai_core.cli import main, build_parser, _map_to_json, _load_json_map, _save_json, _save_otbm
from ai_core.otbm_types import MapData, TileData, Position, TownData, WaypointData
from ai_core.otbm_writer import OTBMWriter
from ai_core.otbm_reader import OTBMReader


def _make_simple_map(w=64, h=64, n_tiles=10):
    """Create a simple MapData for testing."""
    tiles = []
    for i in range(n_tiles):
        tiles.append(TileData(x=i, y=i, z=7, ground_id=102))
    return MapData(width=w, height=h, description="Test Map", tiles=tiles)


def _write_test_otbm(tmp_path, name="test.otbm", w=64, h=64, n_tiles=10):
    """Write a simple OTBM file for testing."""
    m = _make_simple_map(w, h, n_tiles)
    path = tmp_path / name
    writer = OTBMWriter(m)
    writer.save(str(path))
    return str(path)


def _write_test_json(tmp_path, name="test.json", w=64, h=64, n_tiles=10):
    """Write a simple JSON map file for testing."""
    m = _make_simple_map(w, h, n_tiles)
    path = tmp_path / name
    _save_json(m, str(path))
    return str(path)


# ═══════════════════════════════════════════════════════════════════════════
# generate terrain
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateTerrain:
    def test_basic_generation(self, tmp_path):
        output = str(tmp_path / "terrain.otbm")
        result = main(["generate", "terrain", "--size", "64", "--seed", "42", "--output", output])
        assert result == 0
        assert os.path.exists(output)
        assert os.path.getsize(output) > 4

    def test_default_output_name(self, tmp_path):
        """Test that default output name is used."""
        old_cwd = os.getcwd()
        os.chdir(str(tmp_path))
        try:
            result = main(["generate", "terrain", "--size", "32", "--seed", "1"])
            assert result == 0
            assert os.path.exists("terrain.otbm")
        finally:
            os.chdir(old_cwd)

    def test_with_biome(self, tmp_path):
        output = str(tmp_path / "forest.otbm")
        result = main(["generate", "terrain", "--size", "64", "--biome", "forest", "--output", output])
        assert result == 0
        assert os.path.exists(output)

    def test_with_water_level(self, tmp_path):
        output = str(tmp_path / "ocean.otbm")
        result = main(["generate", "terrain", "--size", "64", "--water-level", "0.8", "--output", output])
        assert result == 0
        assert os.path.exists(output)

    def test_terrain_alias(self, tmp_path):
        output = str(tmp_path / "t.otbm")
        result = main(["gen", "t", "--size", "32", "--output", output])
        assert result == 0
        assert os.path.exists(output)


# ═══════════════════════════════════════════════════════════════════════════
# generate dungeon
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateDungeon:
    def test_basic_dungeon(self, tmp_path):
        output = str(tmp_path / "dungeon.otbm")
        result = main(["generate", "dungeon", "--size", "50", "--rooms", "8", "--output", output])
        assert result == 0
        assert os.path.exists(output)
        assert os.path.getsize(output) > 4

    def test_with_floors(self, tmp_path):
        output = str(tmp_path / "multifloor.otbm")
        result = main(["generate", "dungeon", "--rooms", "5", "--floors", "3", "--output", output])
        assert result == 0
        assert os.path.exists(output)

    def test_dungeon_alias(self, tmp_path):
        output = str(tmp_path / "d.otbm")
        result = main(["gen", "d", "--rooms", "4", "--output", output])
        assert result == 0
        assert os.path.exists(output)


# ═══════════════════════════════════════════════════════════════════════════
# generate ai
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateAI:
    def test_basic_ai_generation(self, tmp_path):
        output = str(tmp_path / "ai_map.otbm")
        result = main(["generate", "ai", "isla con bosque", "--output", output])
        assert result == 0
        assert os.path.exists(output)

    def test_ai_no_prompt_returns_error(self, tmp_path):
        result = main(["generate", "ai"])
        assert result == 1

    def test_ai_alias(self, tmp_path):
        output = str(tmp_path / "a.otbm")
        result = main(["gen", "a", "ciudad amurallada", "--output", output])
        assert result == 0
        assert os.path.exists(output)


# ═══════════════════════════════════════════════════════════════════════════
# validate
# ═══════════════════════════════════════════════════════════════════════════

class TestValidate:
    def test_validate_valid_map(self, tmp_path):
        filepath = _write_test_otbm(tmp_path, "valid.otbm")
        result = main(["validate", filepath])
        assert result == 0

    def test_validate_missing_file(self, tmp_path):
        result = main(["validate", str(tmp_path / "nonexistent.otbm")])
        assert result == 1

    def test_validate_alias(self, tmp_path):
        filepath = _write_test_otbm(tmp_path, "val.otbm")
        result = main(["val", filepath])
        assert result == 0

    def test_validate_short_alias(self, tmp_path):
        filepath = _write_test_otbm(tmp_path, "v.otbm")
        result = main(["v", filepath])
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# info
# ═══════════════════════════════════════════════════════════════════════════

class TestInfo:
    def test_info_otbm(self, tmp_path, capsys):
        filepath = _write_test_otbm(tmp_path, "info.otbm", n_tiles=5)
        result = main(["info", filepath])
        assert result == 0
        captured = capsys.readouterr()
        assert "Test Map" in captured.out
        assert "Tiles:" in captured.out

    def test_info_missing_file(self, tmp_path):
        result = main(["info", str(tmp_path / "missing.otbm")])
        assert result == 1

    def test_info_json(self, tmp_path, capsys):
        filepath = _write_test_json(tmp_path, "info.json")
        result = main(["info", filepath])
        assert result == 0

    def test_info_alias(self, tmp_path):
        filepath = _write_test_otbm(tmp_path, "i.otbm")
        result = main(["i", filepath])
        assert result == 0


# ═══════════════════════════════════════════════════════════════════════════
# convert
# ═══════════════════════════════════════════════════════════════════════════

class TestConvert:
    def test_otbm_to_json(self, tmp_path, capsys):
        otbm_file = _write_test_otbm(tmp_path, "conv.otbm", n_tiles=5)
        json_file = str(tmp_path / "conv.json")
        result = main(["convert", otbm_file, "--format", "json", "--output", json_file])
        assert result == 0
        assert os.path.exists(json_file)
        # Verify JSON content
        with open(json_file) as f:
            data = json.load(f)
        assert "tiles" in data
        assert len(data["tiles"]) > 0

    def test_json_to_otbm(self, tmp_path):
        json_file = _write_test_json(tmp_path, "back.otbm.json", n_tiles=5)
        otbm_file = str(tmp_path / "back.otbm")
        result = main(["convert", json_file, "--format", "otbm", "--output", otbm_file])
        assert result == 0
        assert os.path.exists(otbm_file)
        assert os.path.getsize(otbm_file) > 4

    def test_otbm_to_json_auto_name(self, tmp_path):
        otbm_file = _write_test_otbm(tmp_path, "auto.otbm", n_tiles=5)
        result = main(["convert", otbm_file, "--format", "json"])
        assert result == 0
        assert os.path.exists(str(tmp_path / "auto.json"))

    def test_json_to_otbm_auto_name(self, tmp_path):
        json_file = _write_test_json(tmp_path, "auto2.json", n_tiles=5)
        result = main(["convert", json_file, "--format", "otbm"])
        assert result == 0
        assert os.path.exists(str(tmp_path / "auto2.otbm"))

    def test_invalid_format(self, tmp_path):
        filepath = _write_test_otbm(tmp_path, "fmt.otbm")
        with pytest.raises(SystemExit):
            main(["convert", filepath, "--format", "yaml"])

    def test_missing_file(self, tmp_path):
        result = main(["convert", str(tmp_path / "missing.otbm"), "--format", "json"])
        assert result == 1

    def test_convert_alias(self, tmp_path):
        otbm_file = _write_test_otbm(tmp_path, "c.otbm", n_tiles=5)
        result = main(["c", otbm_file, "--format", "json", "--output", str(tmp_path / "c.json")])
        assert result == 0

    def test_roundtrip_otbm_json_otbm(self, tmp_path):
        """Verify data integrity: OTBM → JSON → OTBM."""
        # Create map with towns, waypoints
        m = MapData(
            width=64, height=64, description="Roundtrip Test",
            tiles=[TileData(x=10, y=10, z=7, ground_id=102)],
            towns=[TownData(id=1, name="TestTown", temple=Position(10, 10, 7))],
            waypoints=[WaypointData(name="wp1", pos=Position(20, 20, 7))],
        )
        otbm1 = str(tmp_path / "rt1.otbm")
        OTBMWriter(m).save(otbm1)

        json_file = str(tmp_path / "rt.json")
        result = main(["convert", otbm1, "--format", "json", "--output", json_file])
        assert result == 0

        otbm2 = str(tmp_path / "rt2.otbm")
        result = main(["convert", json_file, "--format", "otbm", "--output", otbm2])
        assert result == 0

        # Read back and verify
        with open(otbm2, "rb") as f:
            reader = OTBMReader(data=f.read())
            final = reader.read()
        assert len(final.tiles) > 0
        assert len(final.towns) == 1
        assert final.towns[0].name == "TestTown"


# ═══════════════════════════════════════════════════════════════════════════
# Utility / Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIUtility:
    def test_no_command_returns_error(self):
        result = main([])
        assert result == 1

    def test_generate_no_subcommand_returns_error(self):
        result = main(["generate"])
        assert result == 1

    def test_version(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_build_parser(self):
        parser = build_parser()
        assert parser.prog == "otbforge"

    def test_map_to_json_dict(self):
        m = _make_simple_map()
        data = _map_to_json(m)
        assert "tiles" in data
        assert len(data["tiles"]) == 10
        assert data["width"] == 64

    def test_load_json_map_roundtrip(self, tmp_path):
        m = _make_simple_map(n_tiles=3)
        json_file = str(tmp_path / "rt.json")
        _save_json(m, json_file)
        loaded = _load_json_map(json_file)
        assert len(loaded.tiles) == 3
        assert loaded.width == 64
