"""Tests for LLM bridge: MapPromptParser, MapCombiner, LLMMapGenerator."""

import os
import pytest
from unittest.mock import patch, MagicMock
from ai_core.llm_bridge import MapPromptParser, MapCombiner, LLMMapGenerator, GeneratorConfig
from ai_core.otbm_types import MapData, TileData, TownData, WaypointData


# ─── MapPromptParser Tests ──────────────────────────────────────────────

class TestMapPromptParser:
    def test_island_default(self):
        configs = MapPromptParser.parse("una isla", seed=42)
        assert len(configs) >= 1
        assert configs[0].generator == "terrain"
        assert configs[0].params["seed"] == 42

    def test_terrain_size(self):
        configs = MapPromptParser.parse("mapa 512x512", seed=42)
        assert len(configs) >= 1
        assert configs[0].generator == "terrain"
        assert configs[0].params["width"] == 512
        assert configs[0].params["height"] == 512

    def test_dungeon_detection(self):
        configs = MapPromptParser.parse("una mazmorra con 10 habitaciones", seed=42)
        dungeons = [c for c in configs if c.generator == "dungeon"]
        assert len(dungeons) == 1
        assert dungeons[0].params["rooms_count"] == 10

    def test_dungeon_floors(self):
        configs = MapPromptParser.parse("dungeon de 3 pisos", seed=42)
        dungeons = [c for c in configs if c.generator == "dungeon"]
        assert len(dungeons) == 1
        assert dungeons[0].params["floors"] == 3

    def test_city_detection(self):
        configs = MapPromptParser.parse("una ciudad amurallada con 15 edificios", seed=42)
        cities = [c for c in configs if c.generator == "city"]
        assert len(cities) == 1
        assert cities[0].params["buildings_count"] == 15
        assert cities[0].params["has_walls"] is True

    def test_city_no_walls(self):
        configs = MapPromptParser.parse("un pueblo con casas", seed=42)
        cities = [c for c in configs if c.generator == "city"]
        assert len(cities) == 1
        assert cities[0].params["has_walls"] is False

    def test_combined_map(self):
        configs = MapPromptParser.parse("una isla con bosque y una ciudad al sur con monstruos", seed=42)
        types = {c.generator for c in configs}
        assert "terrain" in types
        assert "city" in types
        assert "spawns" in types

    def test_empty_prompt(self):
        configs = MapPromptParser.parse("", seed=42)
        assert len(configs) >= 1
        assert configs[0].generator == "terrain"  # Default

    def test_castle(self):
        configs = MapPromptParser.parse("un castillo fortaleza", seed=42)
        cities = [c for c in configs if c.generator == "city"]
        assert len(cities) == 1

    def test_seed_extraction(self):
        configs = MapPromptParser.parse("isla seed=12345")
        assert configs[0].params["seed"] == 12345

    def test_forest_biome(self):
        configs = MapPromptParser.parse("isla con bosque", seed=42)
        terrains = [c for c in configs if c.generator == "terrain"]
        assert len(terrains) == 1

    def test_reproducible_seed(self):
        c1 = MapPromptParser.parse("isla", seed=100)
        c2 = MapPromptParser.parse("isla", seed=100)
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.generator == b.generator
            assert a.params.get("seed") == b.params.get("seed")


# ─── MapCombiner Tests ───────────────────────────────────────────────────

def _make_tile(x, y, z=0, ground=102):
    return TileData(x=x, y=y, z=z, ground_id=ground)

def _make_map(tiles, desc="test", w=64, h=64):
    return MapData(width=w, height=h, description=desc, tiles=tiles)


class TestMapCombiner:
    def test_empty_combine(self):
        result = MapCombiner.combine()
        assert result.width == 256

    def test_single_map(self):
        m = _make_map([_make_tile(0, 0)])
        result = MapCombiner.combine(m)
        assert len(result.tiles) == 1

    def test_overlay_mode(self):
        m1 = _make_map([_make_tile(10, 10, 0, 102)])
        m2 = _make_map([_make_tile(10, 10, 0, 3326)])
        result = MapCombiner.combine(m1, m2, mode="overlay")
        assert len(result.tiles) == 2

    def test_side_by_side_mode(self):
        m1 = _make_map([_make_tile(5, 5, 0, 102)])
        m2 = _make_map([_make_tile(5, 5, 0, 3326)])
        result = MapCombiner.combine(m1, m2, mode="side_by_side")
        assert result.width == 128
        grounds = {t.ground_id for t in result.tiles}
        assert 102 in grounds
        assert 3326 in grounds

    def test_merge_mode(self):
        m1 = _make_map([_make_tile(10, 10, 0, 102)])
        m2 = _make_map([_make_tile(10, 10, 0, 3326)])
        result = MapCombiner.combine(m1, m2, mode="merge")
        assert len(result.tiles) == 1
        assert result.tiles[0].ground_id == 3326

    def test_merge_towns(self):
        m1 = MapData(width=64, height=64, description="t1", towns=[TownData(id=1, name="Thais", temple=(100, 100, 7))])
        m2 = MapData(width=64, height=64, description="t2", towns=[TownData(id=2, name="Carlin", temple=(200, 200, 7))])
        result = MapCombiner.combine(m1, m2, mode="merge")
        assert len(result.towns) == 2

    def test_merge_waypoints(self):
        m1 = MapData(width=64, height=64, description="w1", waypoints=[WaypointData(name="wp1", pos=(50, 50, 7))])
        m2 = MapData(width=64, height=64, description="w2", waypoints=[WaypointData(name="wp2", pos=(150, 150, 7))])
        result = MapCombiner.combine(m1, m2, mode="merge")
        assert len(result.waypoints) == 2


# ─── LLMMapGenerator Tests ──────────────────────────────────────────────

class TestLLMMapGenerator:
    def test_generate_island(self):
        gen = LLMMapGenerator()
        result = gen.generate("una isla 64x64 con bosque", seed=42)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_generate_dungeon(self):
        gen = LLMMapGenerator()
        result = gen.generate("una mazmorra con 5 habitaciones", seed=42)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_generate_city(self):
        gen = LLMMapGenerator()
        result = gen.generate("una ciudad amurallada", seed=42)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_save_to_file(self, tmp_path):
        gen = LLMMapGenerator()
        output = str(tmp_path / "test_map.otbm")
        result = gen.generate("isla 32x32", output_file=output, seed=42)
        assert isinstance(result, MapData)
        assert os.path.exists(output)
        assert os.path.getsize(output) > 4

    def test_llm_mock_fallback(self):
        """Even with mock API that fails, should fall back to pattern parsing."""
        gen = LLMMapGenerator(api_key="test-key", base_url="http://localhost:8000/v1")
        result = gen.generate("isla", seed=42)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0
