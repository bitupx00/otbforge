"""Tests for OTBForge new features: Map Diff Tool, Quest Generator, Biome Analyzer.

Covers all three features with 30+ tests including:
  - MapDiff: TileDiff, StatsDiff, MapDiffResult, compare, compare_files, JSON output
  - QuestGenerator: QuestTemplate, all 12 templates, room generation, standalone mode
  - BiomeAnalyzer: BiomeType, classification, BiomeReport, transition zones, heatmap
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ai_core.models import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TownData,
    WaypointData,
    HouseData,
)

# ===========================================================================
# MAP DIFF TESTS (10+ tests)
# ===========================================================================


class TestTileDiff:
    """Tests for TileDiff dataclass."""

    def test_tile_diff_creation(self):
        from ai_core.map_diff import TileDiff
        td = TileDiff(
            coord=(10, 20, 7), change_type="added",
            ground_after=102, items_after=2,
        )
        assert td.coord == (10, 20, 7)
        assert td.change_type == "added"
        assert td.ground_after == 102
        assert td.items_after == 2

    def test_tile_diff_repr(self):
        from ai_core.map_diff import TileDiff
        td = TileDiff(coord=(5, 5, 0), change_type="removed", ground_before=103)
        r = repr(td)
        assert "removed" in r
        assert "(5, 5, 0)" in r


class TestStatsDiff:
    """Tests for StatsDiff dataclass."""

    def test_stats_diff_defaults(self):
        from ai_core.map_diff import StatsDiff
        sd = StatsDiff()
        assert sd.tiles_before == 0
        assert sd.tiles_after == 0
        assert sd.towns_added == []
        assert sd.towns_removed == []

    def test_stats_diff_deltas(self):
        from ai_core.map_diff import StatsDiff
        sd = StatsDiff(tiles_before=100, tiles_after=150, spawns_before=5, spawns_after=8)
        assert sd.tiles_delta == 50
        assert sd.spawns_delta == 3
        assert sd.houses_delta == 0


class TestMapDiffResult:
    """Tests for MapDiffResult."""

    def test_empty_diff_summary(self):
        from ai_core.map_diff import MapDiffResult
        result = MapDiffResult(map_a_description="Map A", map_b_description="Map B")
        summary = result.summary()
        assert "Map A" in summary
        assert "Map B" in summary
        assert "+0 -0 ~0" in summary

    def test_empty_diff_detailed(self):
        from ai_core.map_diff import MapDiffResult
        result = MapDiffResult(map_a_description="A", map_b_description="B")
        detailed = result.detailed()
        assert "no tile differences" in detailed

    def test_diff_to_json(self):
        from ai_core.map_diff import MapDiffResult, TileDiff
        result = MapDiffResult(
            map_a_description="Old",
            map_b_description="New",
            tile_diffs=[TileDiff(coord=(1, 1, 0), change_type="added", ground_after=102)],
        )
        j = result.to_json()
        assert j["map_a"] == "Old"
        assert j["map_b"] == "New"
        assert j["tile_changes"]["added"] == 1
        assert j["tile_changes"]["removed"] == 0
        assert len(j["tiles"]) == 1
        assert j["tiles"][0]["change"] == "added"


class TestMapDiffCompare:
    """Tests for MapDiff.compare() with actual MapData objects."""

    def test_identical_maps(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="Test", tiles=[
            TileData(x=10, y=10, z=7, ground_id=102),
            TileData(x=11, y=10, z=7, ground_id=103),
        ])
        map_b = MapData(description="Test", tiles=[
            TileData(x=10, y=10, z=7, ground_id=102),
            TileData(x=11, y=10, z=7, ground_id=103),
        ])
        result = MapDiff.compare(map_a, map_b)
        assert len(result.tile_diffs) == 0

    def test_tile_added(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", tiles=[TileData(x=5, y=5, z=7, ground_id=102)])
        map_b = MapData(description="B", tiles=[
            TileData(x=5, y=5, z=7, ground_id=102),
            TileData(x=6, y=5, z=7, ground_id=103),
        ])
        result = MapDiff.compare(map_a, map_b)
        added = [d for d in result.tile_diffs if d.change_type == "added"]
        assert len(added) == 1
        assert added[0].coord == (6, 5, 7)

    def test_tile_removed(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", tiles=[
            TileData(x=5, y=5, z=7, ground_id=102),
            TileData(x=6, y=5, z=7, ground_id=103),
        ])
        map_b = MapData(description="B", tiles=[TileData(x=5, y=5, z=7, ground_id=102)])
        result = MapDiff.compare(map_a, map_b)
        removed = [d for d in result.tile_diffs if d.change_type == "removed"]
        assert len(removed) == 1
        assert removed[0].coord == (6, 5, 7)

    def test_tile_modified_ground(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", tiles=[TileData(x=5, y=5, z=7, ground_id=102)])
        map_b = MapData(description="B", tiles=[TileData(x=5, y=5, z=7, ground_id=103)])
        result = MapDiff.compare(map_a, map_b)
        modified = [d for d in result.tile_diffs if d.change_type == "modified"]
        assert len(modified) == 1
        assert modified[0].ground_before == 102
        assert modified[0].ground_after == 103

    def test_tile_modified_items(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", tiles=[TileData(x=5, y=5, z=7, ground_id=102)])
        map_b = MapData(description="B", tiles=[TileData(
            x=5, y=5, z=7, ground_id=102, items=[ItemData(id=3756)]
        )])
        result = MapDiff.compare(map_a, map_b)
        modified = [d for d in result.tile_diffs if d.change_type == "modified"]
        assert len(modified) == 1
        assert modified[0].items_before == 0
        assert modified[0].items_after == 1

    def test_tile_modified_flags(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", tiles=[TileData(x=5, y=5, z=7, ground_id=102)])
        map_b = MapData(description="B", tiles=[TileData(
            x=5, y=5, z=7, ground_id=102, flags=TileFlag.PROTECTIONZONE
        )])
        result = MapDiff.compare(map_a, map_b)
        modified = [d for d in result.tile_diffs if d.change_type == "modified"]
        assert len(modified) == 1
        assert modified[0].flags_after == int(TileFlag.PROTECTIONZONE)

    def test_town_changes(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", towns=[
            TownData(id=1, name="Thais", temple=Position(100, 100, 7)),
        ])
        map_b = MapData(description="B", towns=[
            TownData(id=1, name="Thais", temple=Position(100, 100, 7)),
            TownData(id=2, name="Carlin", temple=Position(200, 200, 7)),
        ])
        result = MapDiff.compare(map_a, map_b)
        assert "Carlin" in result.stats_diff.towns_added
        assert len(result.stats_diff.towns_removed) == 0

    def test_waypoint_changes(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", waypoints=[
            WaypointData(name="wp1", pos=Position(10, 10, 7)),
        ])
        map_b = MapData(description="B", waypoints=[
            WaypointData(name="wp2", pos=Position(20, 20, 7)),
        ])
        result = MapDiff.compare(map_a, map_b)
        assert "wp1" in result.stats_diff.waypoints_removed
        assert "wp2" in result.stats_diff.waypoints_added

    def test_spawn_changes_in_stats(self):
        from ai_core.map_diff import MapDiff
        map_a = MapData(description="A", spawns=[SpawnData(x=100, y=100, z=7, radius=10)])
        map_b = MapData(description="B", spawns=[
            SpawnData(x=100, y=100, z=7, radius=10),
            SpawnData(x=200, y=200, z=7, radius=15),
        ])
        result = MapDiff.compare(map_a, map_b)
        assert result.stats_diff.spawns_before == 1
        assert result.stats_diff.spawns_after == 2


# ===========================================================================
# QUEST GENERATOR TESTS (12+ tests)
# ===========================================================================


class TestQuestTemplate:
    """Tests for QuestTemplate and predefined templates."""

    def test_base_template_defaults(self):
        from ai_core.generators.quest import QuestTemplate
        qt = QuestTemplate(name="Test Quest", description="A test")
        assert qt.name == "Test Quest"
        assert qt.required_level == 20
        assert qt.difficulty.value == "medium"
        assert qt.num_challenge_rooms == 3
        assert len(qt.reward_items) >= 1

    def test_template_repr(self):
        from ai_core.generators.quest import QuestTemplate
        qt = QuestTemplate(name="Test", description="desc", required_level=50)
        r = repr(qt)
        assert "Test" in r
        assert "50" in r

    def test_dragon_slayer_quest(self):
        from ai_core.generators.quest import DragonSlayerQuest
        q = DragonSlayerQuest()
        assert q.boss_monster == "Dragon Lord"
        assert q.required_level == 50
        assert q.difficulty.value == "hard"
        assert len(q.challenge_monsters) > 0

    def test_tomb_raider_quest(self):
        from ai_core.generators.quest import TombRaiderQuest
        q = TombRaiderQuest()
        assert q.boss_monster == "Mummy Pharaoh"
        assert "Tomb" in q.name

    def test_demon_crypt_quest(self):
        from ai_core.generators.quest import DemonCryptQuest
        q = DemonCryptQuest()
        assert q.difficulty.value == "legendary"
        assert q.required_level == 80

    def test_pirate_cove_quest(self):
        from ai_core.generators.quest import PirateCoveQuest
        q = PirateCoveQuest()
        assert q.difficulty.value == "easy"
        assert q.required_level == 15

    def test_all_12_templates(self):
        from ai_core.generators.quest import QuestGenerator
        templates = QuestGenerator.get_templates()
        assert len(templates) == 12
        names = [t.name for t in templates]
        assert "Dragon's Lair" in names
        assert "Tomb of the Pharaoh" in names

    def test_all_templates_have_required_fields(self):
        from ai_core.generators.quest import QuestGenerator
        for t in QuestGenerator.get_templates():
            assert t.name, f"Template missing name"
            assert t.description, f"Template {t.name} missing description"
            assert t.boss_monster, f"Template {t.name} missing boss_monster"
            assert t.required_level > 0, f"Template {t.name} has invalid level"
            assert len(t.challenge_monsters) > 0, f"Template {t.name} has no monsters"


class TestQuestDifficulty:
    """Tests for QuestDifficulty enum."""

    def test_difficulty_levels(self):
        from ai_core.generators.quest import QuestDifficulty
        assert QuestDifficulty.EASY.value == "easy"
        assert QuestDifficulty.MEDIUM.value == "medium"
        assert QuestDifficulty.HARD.value == "hard"
        assert QuestDifficulty.LEGENDARY.value == "legendary"
        assert len(QuestDifficulty) == 4


class TestQuestRoomType:
    """Tests for QuestRoomType enum."""

    def test_room_types(self):
        from ai_core.generators.quest import QuestRoomType
        assert QuestRoomType.ENTRY.value == "entry"
        assert QuestRoomType.CHALLENGE.value == "challenge"
        assert QuestRoomType.BOSS.value == "boss"
        assert QuestRoomType.REWARD.value == "reward"
        assert QuestRoomType.CORRIDOR.value == "corridor"
        assert len(QuestRoomType) == 5


class TestQuestGenerator:
    """Tests for QuestGenerator."""

    def test_generate_standalone(self):
        from ai_core.generators.quest import QuestGenerator, DragonSlayerQuest
        gen = QuestGenerator(seed=123)
        map_data = gen.generate_standalone(DragonSlayerQuest())
        assert map_data.description == "Quest: Dragon's Lair"
        assert len(map_data.tiles) > 0

    def test_generate_adds_tiles_to_map(self):
        from ai_core.generators.quest import QuestGenerator, SpiderNestQuest
        gen = QuestGenerator(seed=42)
        map_data = MapData(description="Base Map")
        gen.generate_quest(map_data, SpiderNestQuest(), position=Position(100, 100, 7))
        assert len(map_data.tiles) > 0

    def test_generate_adds_spawns(self):
        from ai_core.generators.quest import QuestGenerator, DragonSlayerQuest
        gen = QuestGenerator(seed=42)
        map_data = MapData(description="Base Map")
        gen.generate_quest(map_data, DragonSlayerQuest(), position=Position(100, 100, 7))
        assert len(map_data.spawns) > 0

    def test_generate_adds_npc_spawns(self):
        from ai_core.generators.quest import QuestGenerator, TombRaiderQuest
        gen = QuestGenerator(seed=42)
        map_data = MapData(description="Base Map")
        gen.generate_quest(map_data, TombRaiderQuest(), position=Position(100, 100, 7))
        # Entry room should have NPC
        assert len(map_data.npc_spawns) >= 1
        npc_names = [n.npc_name for n in map_data.npc_spawns]
        assert "Archaeologist Jones" in npc_names

    def test_standalone_map_size(self):
        from ai_core.generators.quest import QuestGenerator, PirateCoveQuest
        gen = QuestGenerator(seed=42)
        map_data = gen.generate_standalone(PirateCoveQuest())
        assert map_data.width >= PirateCoveQuest().area_width
        assert map_data.height >= PirateCoveQuest().area_height

    def test_deterministic_seed(self):
        from ai_core.generators.quest import QuestGenerator, OrcFortressQuest
        gen1 = QuestGenerator(seed=999)
        map1 = gen1.generate_standalone(OrcFortressQuest())
        gen2 = QuestGenerator(seed=999)
        map2 = gen2.generate_standalone(OrcFortressQuest())
        # Same seed should produce same tile count
        assert len(map1.tiles) == len(map2.tiles)

    def test_custom_template(self):
        from ai_core.generators.quest import QuestGenerator, QuestTemplate
        custom = QuestTemplate(
            name="Custom Quest",
            description="A custom quest",
            required_level=5,
            boss_monster="Goblin King",
            challenge_monsters=["goblin"],
            entry_npc_name="Village Chief",
            num_challenge_rooms=2,
            area_width=20,
            area_height=20,
        )
        gen = QuestGenerator(seed=42)
        map_data = gen.generate_standalone(custom)
        assert len(map_data.tiles) > 0


# ===========================================================================
# BIOME ANALYZER TESTS (10+ tests)
# ===========================================================================


class TestBiomeType:
    """Tests for BiomeType enum."""

    def test_biome_types(self):
        from ai_core.biome_analyzer import BiomeType
        expected = ["grass", "forest", "dirt", "sand", "snow", "water",
                     "stone", "lava", "indoor", "unknown"]
        for name in expected:
            assert name in [b.value for b in BiomeType]

    def test_biome_type_count(self):
        from ai_core.biome_analyzer import BiomeType
        assert len(BiomeType) == 10


class TestBiomeClassification:
    """Tests for ground ID to biome classification."""

    def test_classify_grass(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(102) == BiomeType.GRASS
        assert BiomeAnalyzer.classify_ground_id(103) == BiomeType.GRASS

    def test_classify_sand(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(231) == BiomeType.SAND
        assert BiomeAnalyzer.classify_ground_id(351) == BiomeType.SAND

    def test_classify_water(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(490) == BiomeType.WATER
        assert BiomeAnalyzer.classify_ground_id(493) == BiomeType.WATER

    def test_classify_stone(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(410) == BiomeType.STONE
        assert BiomeAnalyzer.classify_ground_id(3326) == BiomeType.STONE

    def test_classify_snow(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(742) == BiomeType.SNOW

    def test_classify_lava(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(884) == BiomeType.LAVA
        assert BiomeAnalyzer.classify_ground_id(5967) == BiomeType.LAVA

    def test_classify_unknown(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(99999) == BiomeType.UNKNOWN
        assert BiomeAnalyzer.classify_ground_id(0) == BiomeType.UNKNOWN

    def test_classify_indoor(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        assert BiomeAnalyzer.classify_ground_id(530) == BiomeType.INDOOR


class TestBiomeReport:
    """Tests for BiomeReport dataclass."""

    def test_empty_report_summary(self):
        from ai_core.biome_analyzer import BiomeReport, BiomeType
        report = BiomeReport()
        summary = report.summary()
        assert "Biome Report" in summary
        assert "0" in summary  # total tiles

    def test_report_to_dict(self):
        from ai_core.biome_analyzer import BiomeReport, BiomeType
        report = BiomeReport(
            total_tiles=100, analyzed_tiles=80,
            dominant_biome=BiomeType.GRASS, dominant_percentage=50.0,
        )
        d = report.to_dict()
        assert d["total_tiles"] == 100
        assert d["dominant_biome"] == "grass"
        assert d["dominant_percentage"] == 50.0


class TestBiomeAnalyzer:
    """Tests for BiomeAnalyzer.detect_biomes()."""

    def test_detect_single_biome(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        map_data = MapData(description="Grass Field", tiles=[
            TileData(x=i, y=j, z=7, ground_id=102) for i in range(5) for j in range(5)
        ])
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert report.total_tiles == 25
        assert report.analyzed_tiles == 25
        assert report.dominant_biome == BiomeType.GRASS
        assert report.dominant_percentage == 100.0

    def test_detect_mixed_biomes(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        tiles = (
            [TileData(x=i, y=0, z=7, ground_id=102) for i in range(10)]  # grass row
            + [TileData(x=i, y=1, z=7, ground_id=231) for i in range(10)]  # sand row
            + [TileData(x=i, y=2, z=7, ground_id=490) for i in range(10)]  # water row
        )
        map_data = MapData(description="Mixed", tiles=tiles)
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert report.analyzed_tiles == 30
        assert BiomeType.GRASS in report.biome_counts
        assert BiomeType.SAND in report.biome_counts
        assert BiomeType.WATER in report.biome_counts

    def test_detect_ignores_no_ground(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        map_data = MapData(description="Empty", tiles=[
            TileData(x=0, y=0, z=7, ground_id=0),
            TileData(x=1, y=0, z=7, ground_id=0),
            TileData(x=2, y=0, z=7, ground_id=102),
        ])
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert report.total_tiles == 3
        assert report.analyzed_tiles == 1

    def test_detect_transition_zones(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        tiles = (
            [TileData(x=i, y=0, z=7, ground_id=102) for i in range(5)]   # grass
            + [TileData(x=i, y=1, z=7, ground_id=231) for i in range(5)]  # sand
        )
        map_data = MapData(description="Transition", tiles=tiles)
        report = BiomeAnalyzer.detect_biomes(map_data, store_heatmap=True)
        # Should have transition zones at the boundary
        assert len(report.transition_zones) > 0

    def test_heatmap_without_data(self):
        from ai_core.biome_analyzer import BiomeAnalyzer
        map_data = MapData(description="Test", tiles=[
            TileData(x=0, y=0, z=7, ground_id=102),
        ])
        report = BiomeAnalyzer.detect_biomes(map_data, store_heatmap=False)
        heatmap = report.heatmap()
        assert "heatmap data not available" in heatmap

    def test_heatmap_with_data(self):
        from ai_core.biome_analyzer import BiomeAnalyzer
        tiles = []
        for y in range(10):
            for x in range(10):
                gid = 102 if y < 5 else 231  # grass top, sand bottom
                tiles.append(TileData(x=x, y=y, z=7, ground_id=gid))
        map_data = MapData(description="HeatMap Test", tiles=tiles)
        report = BiomeAnalyzer.detect_biomes(map_data, store_heatmap=True)
        heatmap = report.heatmap(resolution=10)
        assert "G" in heatmap  # grass symbol
        assert "S" in heatmap  # sand symbol

    def test_dungeon_biome(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        map_data = MapData(description="Dungeon", tiles=[
            TileData(x=i, y=j, z=7, ground_id=410) for i in range(5) for j in range(5)
        ])
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert report.dominant_biome == BiomeType.STONE

    def test_forest_detection_via_items(self):
        from ai_core.biome_analyzer import BiomeAnalyzer, BiomeType
        # Ground is grass but has tree items -> should be forest
        map_data = MapData(description="Forest", tiles=[
            TileData(x=0, y=0, z=7, ground_id=102, items=[ItemData(id=2700)]),  # tree
            TileData(x=1, y=0, z=7, ground_id=102),
        ])
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert BiomeType.FOREST in report.biome_counts

    def test_ground_id_counts(self):
        from ai_core.biome_analyzer import BiomeAnalyzer
        tiles = (
            [TileData(x=i, y=0, z=7, ground_id=102) for i in range(3)]
            + [TileData(x=i, y=1, z=7, ground_id=231) for i in range(2)]
        )
        map_data = MapData(description="Counts", tiles=tiles)
        report = BiomeAnalyzer.detect_biomes(map_data)
        assert report.ground_id_counts[102] == 3
        assert report.ground_id_counts[231] == 2
