"""Tests for LLM bridge: PromptEngine, SchemaParser, MapComposer, LLMBridge, MapSchema."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from ai_core.llm_bridge import (
    LLMBridge,
    MapSchema,
    MapZone,
    MapComposer,
    PromptEngine,
    SchemaParser,
    MapCombiner,
    LLMMapGenerator,
    GeneratorConfig,
    MapPromptParser,
    ZoneBuilding,
    ZoneNPC,
    ZoneSpawn,
    ZoneRoom,
    TIBIA_ITEMS,
)
from ai_core.otbm_types import MapData, TileData, TownData, WaypointData, SpawnData, NPCSpawnData


# ═══════════════════════════════════════════════════════════════════════════
# PromptEngine Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptEngine:
    def test_build_system_prompt_contains_item_db(self):
        prompt = PromptEngine.build_system_prompt()
        assert "Tibia map architect" in prompt
        assert "grass" in prompt
        assert "stone wall" in prompt

    def test_build_system_prompt_contains_schema_structure(self):
        prompt = PromptEngine.build_system_prompt()
        assert "zones" in prompt
        assert "terrain" in prompt
        assert "buildings" in prompt
        assert "npcs" in prompt

    def test_build_user_prompt_basic(self):
        prompt = PromptEngine.build_user_prompt("A castle town")
        assert "castle town" in prompt
        assert "255" in prompt  # 256-1 coordinate hint

    def test_build_user_prompt_with_terrain(self):
        prompt = PromptEngine.build_user_prompt("island", terrain_type="mountain")
        assert "mountain" in prompt
        assert "Preferred terrain type: mountain" in prompt

    def test_build_user_prompt_with_size(self):
        prompt = PromptEngine.build_user_prompt("forest", size=512)
        assert "512" in prompt
        assert "511" in prompt  # 512-1 coordinate hint

    def test_build_user_prompt_default_size(self):
        prompt = PromptEngine.build_user_prompt("desert")
        assert "255" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# MapSchema Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMapSchema:
    def test_default_schema(self):
        schema = MapSchema()
        assert schema.terrain["type"] == "island"
        assert schema.map_width == 256
        assert schema.map_height == 256
        assert schema.zones == []

    def test_from_dict_minimal(self):
        data = {"terrain": {"type": "continent", "size": 128}}
        schema = MapSchema.from_dict(data)
        assert schema.terrain["type"] == "continent"
        assert schema.map_width == 128
        assert schema.map_height == 128

    def test_from_dict_with_zones(self):
        data = {
            "terrain": {"type": "island"},
            "zones": [{
                "name": "castle_town",
                "type": "town",
                "center": {"x": 128, "y": 128},
                "radius": 15,
                "buildings": [
                    {"type": "castle", "tiles": [[100, 100], [110, 110]], "wall_id": 1010, "floor_id": 410, "door_id": 5121}
                ],
                "npcs": [{"name": "Merchant", "x": 105, "y": 105, "z": 7, "npc_id": "merchant"}],
                "spawns": [{"monster": "Rat", "x": 130, "y": 130, "z": 7, "radius": 3}],
                "rooms": [],
                "floors": 1,
            }],
        }
        schema = MapSchema.from_dict(data)
        assert len(schema.zones) == 1
        assert schema.zones[0].name == "castle_town"
        assert len(schema.zones[0].buildings) == 1
        assert schema.zones[0].buildings[0].wall_id == 1010
        assert len(schema.zones[0].npcs) == 1
        assert len(schema.zones[0].spawns) == 1

    def test_to_dict_roundtrip(self):
        schema = MapSchema(
            terrain={"type": "forest", "biomes": ["forest"], "size": 128},
            description="Forest map",
            map_width=128,
            map_height=128,
            zones=[MapZone(name="glen", type="forest", center={"x": 64, "y": 64}, radius=10)],
        )
        data = schema.to_dict()
        assert data["terrain"]["type"] == "forest"
        assert data["map_width"] == 128
        assert len(data["zones"]) == 1
        assert data["zones"][0]["name"] == "glen"


# ═══════════════════════════════════════════════════════════════════════════
# SchemaParser Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaParser:
    def test_parse_empty_schema(self):
        schema = MapSchema()
        result = SchemaParser.parse(schema)
        assert isinstance(result, MapData)
        assert len(result.tiles) == 0

    def test_parse_town_zone(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="town", type="town",
                center={"x": 128, "y": 128}, radius=5,
            )],
        )
        result = SchemaParser.parse(schema)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0
        # All tiles should have ground
        ground_tiles = [t for t in result.tiles if t.ground_id > 0]
        assert len(ground_tiles) > 0

    def test_parse_zone_with_building(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="fortress", type="town",
                center={"x": 100, "y": 100}, radius=5,
                buildings=[ZoneBuilding(
                    type="castle", tiles=[[95, 95, 100, 100]],
                    wall_id=1010, floor_id=410, door_id=5121,
                )],
            )],
        )
        result = SchemaParser.parse(schema)
        assert len(result.tiles) > 0

    def test_parse_zone_with_npcs(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="town", type="town",
                center={"x": 50, "y": 50}, radius=3,
                npcs=[ZoneNPC(name="Merchant", x=50, y=50, z=7)],
            )],
        )
        result = SchemaParser.parse(schema)
        assert len(result.npc_spawns) == 1
        assert result.npc_spawns[0].npc_name == "Merchant"

    def test_parse_zone_with_spawns(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="dungeon", type="town",
                center={"x": 50, "y": 50}, radius=3,
                spawns=[ZoneSpawn(monster="Dragon", x=50, y=55, z=7, radius=5)],
            )],
        )
        result = SchemaParser.parse(schema)
        assert len(result.spawns) == 1
        assert result.spawns[0].monsters[0][0] == "Dragon"

    def test_parse_dungeon_rooms(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="cave", type="dungeon",
                center={"x": 50, "y": 50}, radius=3,
                rooms=[ZoneRoom(type="boss", z=8, x=45, y=45, w=5, h=5, monsters=["Dragon Lord"])],
            )],
        )
        result = SchemaParser.parse(schema)
        # Check underground tiles
        underground = [t for t in result.tiles if t.z >= 8]
        assert len(underground) > 0

    def test_parse_json_string(self):
        json_str = json.dumps({
            "terrain": {"type": "island", "size": 64},
            "zones": [{
                "name": "village", "type": "town",
                "center": {"x": 32, "y": 32}, "radius": 5,
            }],
        })
        result = SchemaParser.parse_json(json_str)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_parse_json_with_markdown(self):
        """LLM may wrap JSON in markdown code blocks."""
        json_str = '```json\n{"terrain": {"type": "island", "size": 64}, "zones": []}\n```'
        result = SchemaParser.parse_json(json_str)
        assert isinstance(result, MapData)

    def test_parse_json_invalid_raises(self):
        with pytest.raises(ValueError, match="No JSON object"):
            SchemaParser._parse_json_to_schema("no json here")

    def test_parse_json_malformed_raises(self):
        with pytest.raises(ValueError):
            SchemaParser._parse_json_to_schema("{broken json")


# ═══════════════════════════════════════════════════════════════════════════
# SchemaParser Validation Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSchemaParserValidation:
    def test_valid_schema_no_errors(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="ok_zone", type="town",
                center={"x": 128, "y": 128}, radius=5,
                buildings=[ZoneBuilding(tiles=[[100, 100, 105, 105]], wall_id=1012, floor_id=410)],
                npcs=[ZoneNPC(name="NPC", x=100, y=100, z=7)],
                spawns=[ZoneSpawn(monster="Rat", x=100, y=100, z=7, radius=3)],
            )],
        )
        errors = SchemaParser.validate_schema(schema)
        assert len(errors) == 0

    def test_invalid_width(self):
        schema = MapSchema(map_width=-1, map_height=256)
        errors = SchemaParser.validate_schema(schema)
        assert len(errors) > 0
        assert any("map_width" in e for e in errors)

    def test_out_of_bounds_center(self):
        schema = MapSchema(
            map_width=100, map_height=100,
            zones=[MapZone(name="bad", type="town", center={"x": 999, "y": 50})],
        )
        errors = SchemaParser.validate_schema(schema)
        assert len(errors) > 0
        assert any("out of bounds" in e for e in errors)

    def test_invalid_npc_z(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="bad_npc", type="town", center={"x": 50, "y": 50},
                npcs=[ZoneNPC(name="X", x=50, y=50, z=20)],
            )],
        )
        errors = SchemaParser.validate_schema(schema)
        assert len(errors) > 0
        assert any("z=" in e for e in errors)

    def test_invalid_item_id(self):
        schema = MapSchema(
            map_width=256, map_height=256,
            zones=[MapZone(
                name="bad_items", type="town", center={"x": 50, "y": 50},
                buildings=[ZoneBuilding(tiles=[[40, 40]], wall_id=99999, floor_id=410)],
            )],
        )
        errors = SchemaParser.validate_schema(schema)
        assert len(errors) > 0
        assert any("invalid item_id" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# MapComposer Tests
# ═══════════════════════════════════════════════════════════════════════════

def _make_schema_with_zone(name="town", ztype="town", cx=64, cy=64, r=10, size=128):
    return MapSchema(
        map_width=size, map_height=size,
        terrain={"type": "island", "biomes": ["plains"], "size": size},
        zones=[MapZone(name=name, type=ztype, center={"x": cx, "y": cy}, radius=r)],
    )


class TestMapComposer:
    def test_compose_without_base(self):
        schema = _make_schema_with_zone()
        result = MapComposer.compose(schema, seed=42)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_compose_with_base_map(self):
        from ai_core.generators.terrain import TerrainGenerator
        base = TerrainGenerator(width=128, height=128, seed=42).generate()
        base_count = len(base.tiles)

        schema = _make_schema_with_zone("my_town", "town", 64, 64, 5, 128)
        result = MapComposer.compose(schema, base_map=base, seed=42)
        assert len(result.tiles) >= base_count
        assert result.width == 128

    def test_compose_merges_npcs(self):
        schema = MapSchema(
            map_width=128, map_height=128,
            zones=[MapZone(
                name="npc_town", type="town", center={"x": 64, "y": 64}, radius=5,
                npcs=[ZoneNPC(name="Merchant", x=64, y=64, z=7)],
            )],
        )
        result = MapComposer.compose(schema, seed=42)
        npc_names = [n.npc_name for n in result.npc_spawns]
        assert "Merchant" in npc_names

    def test_compose_merges_spawns(self):
        schema = MapSchema(
            map_width=128, map_height=128,
            zones=[MapZone(
                name="spawn_zone", type="town", center={"x": 64, "y": 64}, radius=5,
                spawns=[ZoneSpawn(monster="Dragon", x=70, y=70, z=7, radius=5)],
            )],
        )
        result = MapComposer.compose(schema, seed=42)
        assert len(result.spawns) == 1

    def test_generate_terrain_forest(self):
        base = MapComposer._generate_terrain("forest", 64, 64, 42)
        assert isinstance(base, MapData)
        assert len(base.tiles) > 0

    def test_generate_terrain_desert(self):
        base = MapComposer._generate_terrain("desert", 64, 64, 42)
        assert isinstance(base, MapData)
        assert len(base.tiles) > 0


# ═══════════════════════════════════════════════════════════════════════════
# LLMBridge Tests (with mock LLM)
# ═══════════════════════════════════════════════════════════════════════════

MOCK_LLM_RESPONSE_CASTLE = json.dumps({
    "description": "Castle town with dragon cave",
    "map_width": 128,
    "map_height": 128,
    "terrain": {"type": "island", "biomes": ["plains", "forest"], "size": 128},
    "zones": [
        {
            "name": "castle_town",
            "type": "town",
            "center": {"x": 64, "y": 64},
            "radius": 15,
            "buildings": [
                {"type": "castle", "tiles": [[55, 55, 65, 65]], "wall_id": 1010, "floor_id": 410, "door_id": 5121, "name": "Castle"}
            ],
            "npcs": [{"name": "Merchant", "x": 60, "y": 70, "z": 7}],
            "spawns": [{"monster": "Dragon", "x": 80, "y": 80, "z": 7, "radius": 5}],
            "rooms": [],
            "floors": 1,
        },
        {
            "name": "dragon_cave",
            "type": "dungeon",
            "center": {"x": 64, "y": 30},
            "radius": 10,
            "floors": 3,
            "rooms": [
                {"type": "boss", "z": 9, "x": 58, "y": 25, "w": 6, "h": 6, "monsters": ["Dragon Lord"]}
            ],
        },
    ],
})


class TestLLMBridge:
    def test_generate_with_mock_llm(self):
        """Test LLMBridge with mocked LLM client."""
        mock_client = lambda sys, usr: MOCK_LLM_RESPONSE_CASTLE

        bridge = LLMBridge(llm_client=mock_client)
        result = bridge.generate_map("A castle town with a dragon cave", size=128)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0
        assert len(result.npc_spawns) >= 1
        assert len(result.spawns) >= 1

    def test_generate_with_mock_llm_has_building_tiles(self):
        mock_client = lambda sys, usr: MOCK_LLM_RESPONSE_CASTLE

        bridge = LLMBridge(llm_client=mock_client)
        result = bridge.generate_map("castle", size=128)
        # Building should have created tiles with wall_id=1010 as items
        wall_items = [t for t in result.tiles for item in t.items if item.id == 1010]
        assert len(wall_items) > 0

    def test_generate_with_mock_llm_has_npc(self):
        mock_client = lambda sys, usr: MOCK_LLM_RESPONSE_CASTLE

        bridge = LLMBridge(llm_client=mock_client)
        result = bridge.generate_map("town", size=128)
        assert any(n.npc_name == "Merchant" for n in result.npc_spawns)

    def test_generate_fallback_to_pattern(self):
        """Without LLM client or API, should fall back to pattern parsing."""
        bridge = LLMBridge()
        result = bridge.generate_map("una isla 64x64 con bosque", size=64)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_generate_fallback_no_api_key(self):
        bridge = LLMBridge(api_key=None, base_url=None)
        result = bridge.generate_map("dungeon con 5 habitaciones", size=64)
        assert isinstance(result, MapData)

    def test_generate_with_invalid_llm_falls_back(self):
        """If LLM fails, should fall back to pattern-based."""
        def bad_client(sys, usr):
            raise RuntimeError("LLM unavailable")

        bridge = LLMBridge(llm_client=bad_client)
        result = bridge.generate_map("isla tropical", size=64)
        assert isinstance(result, MapData)
        assert len(result.tiles) > 0

    def test_generate_with_empty_json_falls_back(self):
        def empty_client(sys, usr):
            return "no json at all"

        bridge = LLMBridge(llm_client=empty_client)
        result = bridge.generate_map("forest map", size=64)
        # Should fall back to pattern-based since JSON parse fails
        assert isinstance(result, MapData)

    def test_bridge_custom_size(self):
        mock_client = lambda sys, usr: json.dumps({
            "terrain": {"type": "island", "size": 64},
            "zones": [],
            "map_width": 64,
            "map_height": 64,
        })
        bridge = LLMBridge(llm_client=mock_client)
        result = bridge.generate_map("small island", size=64)
        assert result.width == 64
        assert result.height == 64


# ═══════════════════════════════════════════════════════════════════════════
# TIBIA_ITEMS Database Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTibiaItemsDB:
    def test_has_ground(self):
        assert "ground" in TIBIA_ITEMS
        assert 102 in TIBIA_ITEMS["ground"]  # grass

    def test_has_walls(self):
        assert "walls" in TIBIA_ITEMS
        assert 1010 in TIBIA_ITEMS["walls"]  # castle wall

    def test_has_floors(self):
        assert "floors" in TIBIA_ITEMS
        assert 410 in TIBIA_ITEMS["floors"]

    def test_has_doors(self):
        assert "doors" in TIBIA_ITEMS
        assert 5121 in TIBIA_ITEMS["doors"]

    def test_has_decorations(self):
        assert "decorations" in TIBIA_ITEMS
        assert 2700 in TIBIA_ITEMS["decorations"]

    def test_all_ids_positive(self):
        for category, items in TIBIA_ITEMS.items():
            for item_id in items:
                assert item_id > 0, f"Invalid item ID {item_id} in {category}"
