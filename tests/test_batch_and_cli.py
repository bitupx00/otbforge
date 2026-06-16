"""Tests for Batch Generator + new CLI subcommands (diff, analyze, batch, quest)."""

import json
import os
import pytest
import sys
from io import StringIO

from ai_core.cli import main, build_parser
from ai_core.batch_generator import (
    BatchConfig, MapGenConfig, generate_batch, generate_from_prompt_list,
    load_batch_config, _parse_batch_config,
)
from ai_core.map_diff import MapDiff, MapDiffResult
from ai_core.biome_analyzer import BiomeAnalyzer, BiomeReport
from ai_core.models import (
    MapData, TileData, ItemData, Position, TownData, WaypointData,
    SpawnData, NPCSpawnData, TileFlag,
)
from ai_core.otbm_writer import OTBMWriter
from ai_core.otbm_reader import OTBMReader
from ai_core.generators.quest import QuestGenerator, DragonSlayerQuest, QuestTemplate


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_map(w=64, h=64, tiles=None, description="Test Map", **kwargs):
    """Create a MapData for testing."""
    if tiles is None:
        tiles = [TileData(x=i, y=i, z=7, ground_id=102) for i in range(10)]
    return MapData(width=w, height=h, description=description, tiles=tiles, **kwargs)


def _write_otbm(tmp_path, map_data=None, name="test.otbm"):
    """Write a MapData to an OTBM file."""
    if map_data is None:
        map_data = _make_map()
    path = str(tmp_path / name)
    writer = OTBMWriter(map_data)
    writer.save(path)
    return path


def _write_json(tmp_path, map_data=None, name="test.json"):
    """Write a MapData to a JSON file."""
    from ai_core.cli import _save_json
    if map_data is None:
        map_data = _make_map()
    path = str(tmp_path / name)
    _save_json(map_data, path)
    return path


# ═══════════════════════════════════════════════════════════════════════════
# BatchConfig & MapGenConfig
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchConfig:
    def test_map_gen_config_defaults(self):
        cfg = MapGenConfig()
        assert cfg.name == "map"
        assert cfg.size == 128
        assert cfg.seed == 42
        assert cfg.generators == ["terrain"]
        assert cfg.output_format == "otbm"

    def test_map_gen_config_custom(self):
        cfg = MapGenConfig(name="dungeon_1", size=64, seed=100, generators=["dungeon"])
        assert cfg.name == "dungeon_1"
        assert cfg.size == 64
        assert cfg.seed == 100
        assert cfg.generators == ["dungeon"]

    def test_batch_config_defaults(self):
        bc = BatchConfig()
        assert bc.output_dir == "./output"
        assert bc.maps == []

    def test_batch_config_with_maps(self):
        bc = BatchConfig(
            output_dir="./maps",
            maps=[MapGenConfig(name="a"), MapGenConfig(name="b")],
        )
        assert len(bc.maps) == 2
        assert bc.maps[0].name == "a"
        assert bc.maps[1].name == "b"

    def test_parse_batch_config_dict(self):
        data = {
            "output_dir": "/tmp/maps",
            "maps": [
                {"name": "forest", "size": 128, "seed": 42},
                {"name": "cave", "size": 64, "seed": 99, "generators": ["dungeon"]},
            ],
        }
        bc = _parse_batch_config(data)
        assert bc.output_dir == "/tmp/maps"
        assert len(bc.maps) == 2
        assert bc.maps[0].name == "forest"
        assert bc.maps[0].generators == ["terrain"]
        assert bc.maps[1].name == "cave"
        assert bc.maps[1].generators == ["dungeon"]

    def test_parse_batch_config_with_biome(self):
        data = {
            "maps": [
                {"name": "desert_map", "biome": "desert", "water_level": 0.0},
            ],
        }
        bc = _parse_batch_config(data)
        assert bc.maps[0].biome == "desert"
        assert bc.maps[0].water_level == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# load_batch_config (JSON)
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadBatchConfig:
    def test_load_json_config(self, tmp_path):
        config_data = {
            "output_dir": str(tmp_path / "out"),
            "maps": [
                {"name": "map_a", "size": 64, "seed": 1},
            ],
        }
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps(config_data))

        bc = load_batch_config(str(config_file))
        assert bc.maps[0].name == "map_a"
        assert bc.maps[0].size == 64

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_batch_config("/nonexistent/config.json")


# ═══════════════════════════════════════════════════════════════════════════
# generate_batch
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateBatch:
    def test_generate_single_terrain_map(self, tmp_path):
        output_dir = str(tmp_path / "batch_out")
        bc = BatchConfig(
            output_dir=output_dir,
            maps=[MapGenConfig(name="test_map", size=32, seed=42)],
        )
        files = generate_batch(bc)
        assert len(files) == 1
        assert os.path.exists(files[0])
        assert files[0].endswith(".otbm")

    def test_generate_multiple_maps(self, tmp_path):
        output_dir = str(tmp_path / "multi")
        bc = BatchConfig(
            output_dir=output_dir,
            maps=[
                MapGenConfig(name="map_0", size=32, seed=1),
                MapGenConfig(name="map_1", size=32, seed=2),
                MapGenConfig(name="map_2", size=32, seed=3),
            ],
        )
        files = generate_batch(bc)
        assert len(files) == 3
        for f in files:
            assert os.path.exists(f)

    def test_generate_dungeon_map(self, tmp_path):
        output_dir = str(tmp_path / "dungeon_batch")
        bc = BatchConfig(
            output_dir=output_dir,
            maps=[MapGenConfig(name="dun", size=32, seed=42, generators=["dungeon"])],
        )
        files = generate_batch(bc)
        assert len(files) == 1
        assert os.path.exists(files[0])

    def test_generate_json_format(self, tmp_path):
        output_dir = str(tmp_path / "json_batch")
        bc = BatchConfig(
            output_dir=output_dir,
            maps=[MapGenConfig(name="json_map", size=32, seed=42, output_format="json")],
        )
        files = generate_batch(bc)
        assert len(files) == 1
        assert files[0].endswith(".json")
        # Verify it's valid JSON
        with open(files[0]) as f:
            data = json.load(f)
        assert "tiles" in data

    def test_progress_callback(self, tmp_path):
        progress_calls = []

        def on_progress(i, total, name, status):
            progress_calls.append((i, total, name, status))

        output_dir = str(tmp_path / "progress")
        bc = BatchConfig(
            output_dir=output_dir,
            maps=[
                MapGenConfig(name="p1", size=32, seed=1),
                MapGenConfig(name="p2", size=32, seed=2),
            ],
        )
        generate_batch(bc, progress_callback=on_progress)
        assert len(progress_calls) == 4  # generating + done for each
        assert progress_calls[0] == (0, 2, "p1", "generating")
        assert progress_calls[1] == (0, 2, "p1", "done")
        assert progress_calls[2] == (1, 2, "p2", "generating")
        assert progress_calls[3] == (1, 2, "p2", "done")

    def test_empty_maps_returns_empty(self, tmp_path):
        bc = BatchConfig(output_dir=str(tmp_path / "empty"), maps=[])
        files = generate_batch(bc)
        assert files == []


# ═══════════════════════════════════════════════════════════════════════════
# generate_from_prompt_list
# ═══════════════════════════════════════════════════════════════════════════

class TestGenerateFromPromptList:
    def test_single_prompt(self, tmp_path):
        files = generate_from_prompt_list(
            ["tropical island"],
            output_dir=str(tmp_path / "prompts"),
            size=64,
            seed=42,
        )
        assert len(files) == 1
        assert os.path.exists(files[0])

    def test_multiple_prompts(self, tmp_path):
        files = generate_from_prompt_list(
            ["forest village", "desert fortress", "snow mountain"],
            output_dir=str(tmp_path / "multi_prompt"),
            size=64,
        )
        assert len(files) == 3
        for f in files:
            assert os.path.exists(f)

    def test_empty_prompts_returns_empty(self, tmp_path):
        files = generate_from_prompt_list(
            [], output_dir=str(tmp_path / "empty_prompts"),
        )
        assert files == []


# ═══════════════════════════════════════════════════════════════════════════
# CLI: diff subcommand
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIDiff:
    def test_diff_identical_maps(self, tmp_path, capsys):
        m = _make_map()
        f1 = _write_otbm(tmp_path, m, "a.otbm")
        f2 = _write_otbm(tmp_path, m, "b.otbm")
        result = main(["diff", f1, f2])
        assert result == 0
        captured = capsys.readouterr()
        assert "Map Diff" in captured.out

    def test_diff_different_maps(self, tmp_path, capsys):
        m1 = _make_map(tiles=[TileData(x=0, y=0, z=7, ground_id=102)])
        m2 = _make_map(tiles=[TileData(x=0, y=0, z=7, ground_id=202)])
        f1 = _write_otbm(tmp_path, m1, "diff1.otbm")
        f2 = _write_otbm(tmp_path, m2, "diff2.otbm")
        result = main(["diff", f1, f2])
        assert result == 0

    def test_diff_json_output(self, tmp_path, capsys):
        m1 = _make_map()
        m2 = _make_map(tiles=[TileData(x=5, y=5, z=7, ground_id=103)])
        f1 = _write_otbm(tmp_path, m1, "j1.otbm")
        f2 = _write_otbm(tmp_path, m2, "j2.otbm")
        result = main(["diff", f1, f2, "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "tile_changes" in data

    def test_diff_detailed(self, tmp_path, capsys):
        m1 = _make_map()
        m2 = _make_map()
        f1 = _write_otbm(tmp_path, m1, "d1.otbm")
        f2 = _write_otbm(tmp_path, m2, "d2.otbm")
        result = main(["diff", f1, f2, "--detailed"])
        assert result == 0

    def test_diff_missing_file(self, tmp_path):
        f1 = _write_otbm(tmp_path, name="exists.otbm")
        result = main(["diff", f1, str(tmp_path / "missing.otbm")])
        assert result == 1

    def test_diff_parser_exists(self):
        parser = build_parser()
        args = parser.parse_args(["diff", "a.otbm", "b.otbm"])
        assert args.command == "diff"
        assert args.map1 == "a.otbm"
        assert args.map2 == "b.otbm"


# ═══════════════════════════════════════════════════════════════════════════
# CLI: analyze subcommand
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIAnalyze:
    def test_analyze_otbm(self, tmp_path, capsys):
        f = _write_otbm(tmp_path, _make_map(), "analyze.otbm")
        result = main(["analyze", f])
        assert result == 0
        captured = capsys.readouterr()
        assert "Biome Report" in captured.out

    def test_analyze_missing_file(self, tmp_path):
        result = main(["analyze", str(tmp_path / "missing.otbm")])
        assert result == 1

    def test_analyze_parser_exists(self):
        parser = build_parser()
        args = parser.parse_args(["analyze", "map.otbm"])
        assert args.command == "analyze"
        assert args.file == "map.otbm"

    def test_analyze_alias(self):
        parser = build_parser()
        args = parser.parse_args(["analysis", "map.otbm"])
        assert args.command == "analysis"


# ═══════════════════════════════════════════════════════════════════════════
# CLI: batch subcommand
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIBatch:
    def test_batch_from_config(self, tmp_path, capsys):
        output_dir = str(tmp_path / "cli_batch")
        config_data = {
            "output_dir": output_dir,
            "maps": [
                {"name": "cli_map_1", "size": 32, "seed": 1},
            ],
        }
        config_file = tmp_path / "cli_batch.json"
        config_file.write_text(json.dumps(config_data))

        result = main(["batch", str(config_file)])
        assert result == 0
        captured = capsys.readouterr()
        assert "Batch complete" in captured.out
        assert os.path.exists(os.path.join(output_dir, "cli_map_1.otbm"))

    def test_batch_missing_config(self, tmp_path):
        result = main(["batch", str(tmp_path / "no_config.json")])
        assert result == 1

    def test_batch_empty_config(self, tmp_path):
        config_data = {"output_dir": str(tmp_path / "empty_batch"), "maps": []}
        config_file = tmp_path / "empty.json"
        config_file.write_text(json.dumps(config_data))
        result = main(["batch", str(config_file)])
        assert result == 1

    def test_batch_parser_exists(self):
        parser = build_parser()
        args = parser.parse_args(["batch", "config.json"])
        assert args.command == "batch"
        assert args.config == "config.json"


# ═══════════════════════════════════════════════════════════════════════════
# CLI: quest subcommand
# ═══════════════════════════════════════════════════════════════════════════

class TestCLIQuest:
    def test_quest_dragon(self, tmp_path, capsys):
        m = _make_map(w=128, h=128, tiles=[])
        map_file = _write_otbm(tmp_path, m, "quest_map.otbm")
        output_file = str(tmp_path / "quest_out.otbm")

        result = main([
            "quest", map_file,
            "--name", "dragon",
            "--position", "10,10,7",
            "--output", output_file,
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Quest" in captured.out
        assert os.path.exists(output_file)

    def test_quest_missing_map(self, tmp_path):
        result = main([
            "quest", str(tmp_path / "missing.otbm"),
            "--position", "10,10,7",
        ])
        assert result == 1

    def test_quest_parser_exists(self):
        parser = build_parser()
        args = parser.parse_args(["quest", "map.otbm", "--position", "100,100,7"])
        assert args.command == "quest"
        assert args.position == "100,100,7"

    def test_quest_dragon_template(self):
        gen = QuestGenerator(seed=42)
        template = DragonSlayerQuest()
        map_data = MapData(width=128, height=128, tiles=[])
        gen.generate_quest(map_data, template, Position(50, 50, 7))
        assert len(map_data.tiles) > 0
        assert len(map_data.spawns) > 0
        assert len(map_data.npc_spawns) > 0

    def test_quest_custom_template(self, tmp_path, capsys):
        m = _make_map(w=128, h=128, tiles=[])
        map_file = _write_otbm(tmp_path, m, "custom_quest.otbm")
        output_file = str(tmp_path / "custom_out.otbm")

        result = main([
            "quest", map_file,
            "--name", "My Custom Quest",
            "--position", "5,5,7",
            "--output", output_file,
        ])
        assert result == 0
        assert os.path.exists(output_file)
