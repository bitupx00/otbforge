"""LLM Bridge — Text prompt → JSON MapSchema → MapData → OTBM.

Architecture:
    1. MapSchema     — JSON schema definition (intermediate format between text and MapData)
    2. PromptEngine  — Builds prompts for the LLM to generate MapSchema JSON
    3. SchemaParser  — Parses LLM JSON response → MapData
    4. MapComposer   — Combines terrain base + LLM-generated elements
    5. LLMBridge     — High-level API: prompt → MapData

Also retains the existing pattern-based parsing (MapPromptParser, MapCombiner,
LLMMapGenerator) for fallback / offline use.
"""

import json
import re
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlags,
    TownData,
    Tiles,
)
from ai_core.generators import TerrainGenerator, DungeonGenerator, CityGenerator, SpawnGenerator


# ═══════════════════════════════════════════════════════════════════════════
# Tibia Item Database — Subset for LLM prompt context
# ═══════════════════════════════════════════════════════════════════════════

TIBIA_ITEMS: Dict[str, Dict[int, str]] = {
    "ground": {
        102: "grass", 103: "dirt", 231: "sand", 490: "water",
        5967: "lava", 7731: "snow", 3326: "stone",
    },
    "walls": {
        1102: "stone wall", 1060: "brick wall", 1018: "wood wall",
        1010: "castle wall", 1012: "house wall", 1015: "pale wall",
    },
    "floors": {
        530: "wood floor", 5565: "red carpet", 410: "tiled floor",
        355: "cobblestone", 389: " paved floor",
    },
    "doors": {
        5121: "closed door", 5122: "open door", 5123: "locked door",
    },
    "decorations": {
        2700: "tree", 2701: "pine tree", 2702: "willow tree",
        2767: "bush", 2768: "hedge", 2740: "flower",
        3756: "chest", 3757: "drawer", 2103: "barrel",
    },
    "containers": {
        3756: "chest", 3757: "drawer", 2853: "crate",
        1740: "mailbox",
    },
    "stairs": {
        433: "stone stairs", 1392: "wooden stairs",
        1396: "ladder",
    },
    "special": {
        1387: "teleport", 1014: "magic wall",
        8568: "campfire",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# MapSchema — JSON structure (what the LLM generates)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ZoneBuilding:
    """A building within a zone."""
    type: str = "house"
    tiles: List[List[int]] = field(default_factory=list)  # [[x1,y1],[x2,y2]]
    wall_id: int = 1012
    floor_id: int = 410
    roof_id: int = 0
    door_id: int = 5121
    name: str = ""


@dataclass
class ZoneNPC:
    """An NPC placement."""
    name: str = "Merchant"
    x: int = 0
    y: int = 0
    z: int = 7
    npc_id: str = ""


@dataclass
class ZoneSpawn:
    """A monster spawn."""
    monster: str = "Rat"
    x: int = 0
    y: int = 0
    z: int = 7
    radius: int = 5


@dataclass
class ZoneRoom:
    """A room within a dungeon zone."""
    type: str = "normal"
    z: int = 8
    x: int = 0
    y: int = 0
    w: int = 5
    h: int = 5
    monsters: List[str] = field(default_factory=list)


@dataclass
class MapZone:
    """A zone in the map schema."""
    name: str = "zone"
    type: str = "town"  # town, dungeon, forest, desert, lake, mountains
    center: Dict[str, int] = field(default_factory=lambda: {"x": 128, "y": 128})
    radius: int = 20
    buildings: List[ZoneBuilding] = field(default_factory=list)
    npcs: List[ZoneNPC] = field(default_factory=list)
    spawns: List[ZoneSpawn] = field(default_factory=list)
    rooms: List[ZoneRoom] = field(default_factory=list)
    floors: int = 1
    ground_id: int = 0


@dataclass
class MapSchema:
    """Top-level map schema — intermediate JSON representation."""
    terrain: Dict[str, Any] = field(default_factory=lambda: {
        "type": "island",
        "biomes": ["plains"],
        "size": 256,
    })
    zones: List[MapZone] = field(default_factory=list)
    description: str = "Generated Map"
    map_width: int = 256
    map_height: int = 256

    @classmethod
    def from_dict(cls, data: dict) -> "MapSchema":
        """Parse a raw dict into MapSchema."""
        terrain = data.get("terrain", {})
        description = data.get("description", "Generated Map")
        map_width = data.get("map_width", terrain.get("size", 256))
        map_height = data.get("map_height", map_width)

        zones = []
        for z_data in data.get("zones", []):
            buildings = [ZoneBuilding(**b) for b in z_data.get("buildings", [])]
            npcs = [ZoneNPC(**n) for n in z_data.get("npcs", [])]
            spawns = [ZoneSpawn(**s) for s in z_data.get("spawns", [])]
            rooms = [ZoneRoom(**r) for r in z_data.get("rooms", [])]
            zone = MapZone(
                name=z_data.get("name", "zone"),
                type=z_data.get("type", "town"),
                center=z_data.get("center", {"x": 128, "y": 128}),
                radius=z_data.get("radius", 20),
                buildings=buildings,
                npcs=npcs,
                spawns=spawns,
                rooms=rooms,
                floors=z_data.get("floors", 1),
                ground_id=z_data.get("ground_id", 0),
            )
            zones.append(zone)

        return cls(
            terrain=terrain,
            zones=zones,
            description=description,
            map_width=map_width,
            map_height=map_height,
        )

    def to_dict(self) -> dict:
        """Serialize to dict for JSON."""
        return {
            "terrain": self.terrain,
            "zones": [
                {
                    "name": z.name, "type": z.type, "center": z.center,
                    "radius": z.radius, "buildings": [
                        {"type": b.type, "tiles": b.tiles, "wall_id": b.wall_id,
                         "floor_id": b.floor_id, "door_id": b.door_id, "name": b.name}
                        for b in z.buildings
                    ],
                    "npcs": [{"name": n.name, "x": n.x, "y": n.y, "z": n.z, "npc_id": n.npc_id} for n in z.npcs],
                    "spawns": [{"monster": s.monster, "x": s.x, "y": s.y, "z": s.z, "radius": s.radius} for s in z.spawns],
                    "rooms": [{"type": r.type, "z": r.z, "x": r.x, "y": r.y, "w": r.w, "h": r.h, "monsters": r.monsters} for r in z.rooms],
                    "floors": z.floors, "ground_id": z.ground_id,
                }
                for z in self.zones
            ],
            "description": self.description,
            "map_width": self.map_width,
            "map_height": self.map_height,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PromptEngine — Constructs prompts for LLM
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a Tibia map architect. Generate OTBM-compatible map schemas from text descriptions.

Output ONLY valid JSON with this structure:
{{
  "description": "Map description",
  "map_width": 256,
  "map_height": 256,
  "terrain": {{
    "type": "island|continent|dungeon|wilderness",
    "biomes": ["plains", "forest", "mountains", "desert", "snow", "swamp"],
    "size": 256
  }},
  "zones": [
    {{
      "name": "zone_name",
      "type": "town|dungeon|forest|desert|lake|mountains",
      "center": {{"x": 128, "y": 128}},
      "radius": 20,
      "ground_id": 0,
      "buildings": [
        {{"type": "castle|house|shop|temple", "tiles": [[x1,y1],[x2,y2]], "wall_id": 1012, "floor_id": 410, "door_id": 5121, "name": "Building Name"}}
      ],
      "npcs": [{{"name": "NPC Name", "x": 125, "y": 128, "z": 7, "npc_id": "merchant"}}],
      "spawns": [{{"monster": "Dragon", "x": 128, "y": 100, "z": 7, "radius": 5}}],
      "rooms": [{{"type": "boss|normal|treasure", "z": 8, "x": 10, "y": 10, "w": 5, "h": 5, "monsters": ["Dragon Lord"]}}],
      "floors": 1
    }}
  ]
}}

Available ground IDs: {grounds}
Available wall IDs: {walls}
Available floor IDs: {floors}
Available door IDs: {doors}
Available decoration IDs: {decorations}
Available container IDs: {containers}

Constraints:
- All coordinates must be within map_width x map_height bounds (0 to map_width-1, 0 to map_height-1)
- Zones should not overlap significantly
- Building tiles define the area covered (top-left to bottom-right corners)
- Item IDs must be from the provided database
- Z-levels: 0-7 = surface, 8-15 = underground

Respond ONLY with valid JSON, no explanation."""


class PromptEngine:
    """Builds system and user prompts for LLM map generation."""

    @staticmethod
    def build_system_prompt() -> str:
        """Build the system prompt with Tibia item database."""
        return SYSTEM_PROMPT.format(
            grounds=json.dumps(TIBIA_ITEMS["ground"]),
            walls=json.dumps(TIBIA_ITEMS["walls"]),
            floors=json.dumps(TIBIA_ITEMS["floors"]),
            doors=json.dumps(TIBIA_ITEMS["doors"]),
            decorations=json.dumps(TIBIA_ITEMS["decorations"]),
            containers=json.dumps(TIBIA_ITEMS["containers"]),
        )

    @staticmethod
    def build_user_prompt(prompt: str, terrain_type: Optional[str] = None,
                          size: int = 256) -> str:
        """Build the user prompt."""
        extra = ""
        if terrain_type:
            extra += f"\nPreferred terrain type: {terrain_type}"
        if size != 256:
            extra += f"\nMap size: {size}x{size}"
        extra += f"\nMap coordinate space: 0 to {size - 1} for both x and y."
        return f"Create a Tibia map: {prompt}{extra}"


# ═══════════════════════════════════════════════════════════════════════════
# SchemaParser — Parses JSON → MapData
# ═══════════════════════════════════════════════════════════════════════════

class SchemaParser:
    """Converts a MapSchema (or raw JSON dict) into a MapData object."""

    # Valid item ID ranges
    MIN_ITEM_ID = 1
    MAX_ITEM_ID = 65535
    MAX_COORD = 65535
    MIN_Z = 0
    MAX_Z = 15

    @classmethod
    def parse(cls, schema: MapSchema) -> MapData:
        """Parse a MapSchema into a MapData."""
        tiles = []
        spawns = []
        npc_spawns = []

        for zone in schema.zones:
            z_tiles, z_spawns, z_npcs = cls._parse_zone(schema.map_width, schema.map_height, zone)
            tiles.extend(z_tiles)
            spawns.extend(z_spawns)
            npc_spawns.extend(z_npcs)

        return MapData(
            width=schema.map_width,
            height=schema.map_height,
            description=schema.description,
            tiles=tiles,
            spawns=spawns,
            npc_spawns=npc_spawns,
        )

    @classmethod
    def parse_json(cls, json_str: str) -> MapData:
        """Parse a JSON string into MapData."""
        schema = cls._parse_json_to_schema(json_str)
        return cls.parse(schema)

    @classmethod
    def _parse_json_to_schema(cls, json_str: str) -> MapSchema:
        """Parse raw JSON string, handling LLM output that may include extra text."""
        # Try to extract JSON from response (may have markdown or explanation)
        json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in LLM response")

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}")

        return MapSchema.from_dict(data)

    @classmethod
    def validate_schema(cls, schema: MapSchema) -> List[str]:
        """Validate a MapSchema and return list of error messages."""
        errors = []
        w, h = schema.map_width, schema.map_height

        if w <= 0 or w > cls.MAX_COORD:
            errors.append(f"Invalid map_width: {w}")
        if h <= 0 or h > cls.MAX_COORD:
            errors.append(f"Invalid map_height: {h}")

        for zone in schema.zones:
            cx = zone.center.get("x", 128)
            cy = zone.center.get("y", 128)
            if not (0 <= cx < w):
                errors.append(f"Zone '{zone.name}': center x={cx} out of bounds (0-{w-1})")
            if not (0 <= cy < h):
                errors.append(f"Zone '{zone.name}': center y={cy} out of bounds (0-{h-1})")

            for building in zone.buildings:
                for tile_coords in building.tiles:
                    if len(tile_coords) >= 2:
                        tx, ty = tile_coords[0], tile_coords[1]
                        if not (0 <= tx < w):
                            errors.append(f"Zone '{zone.name}' building '{building.name}': tile x={tx} out of bounds")
                        if not (0 <= ty < h):
                            errors.append(f"Zone '{zone.name}' building '{building.name}': tile y={ty} out of bounds")

                cls._validate_item_id(errors, zone.name, building.wall_id, f"building wall")
                cls._validate_item_id(errors, zone.name, building.floor_id, f"building floor")
                cls._validate_item_id(errors, zone.name, building.door_id, f"building door")

            for npc in zone.npcs:
                if not (0 <= npc.x < w):
                    errors.append(f"Zone '{zone.name}' NPC '{npc.name}': x={npc.x} out of bounds")
                if not (0 <= npc.y < h):
                    errors.append(f"Zone '{zone.name}' NPC '{npc.name}': y={npc.y} out of bounds")
                if not (cls.MIN_Z <= npc.z <= cls.MAX_Z):
                    errors.append(f"Zone '{zone.name}' NPC '{npc.name}': z={npc.z} out of range")

            for spawn in zone.spawns:
                if not (0 <= spawn.x < w):
                    errors.append(f"Zone '{zone.name}' spawn '{spawn.monster}': x={spawn.x} out of bounds")
                if not (0 <= spawn.y < h):
                    errors.append(f"Zone '{zone.name}' spawn '{spawn.monster}': y={spawn.y} out of bounds")
                if not (cls.MIN_Z <= spawn.z <= cls.MAX_Z):
                    errors.append(f"Zone '{zone.name}' spawn '{spawn.monster}': z={spawn.z} out of range")

            for room in zone.rooms:
                if not (cls.MIN_Z <= room.z <= cls.MAX_Z):
                    errors.append(f"Zone '{zone.name}' room: z={room.z} out of range")

        return errors

    @classmethod
    def _validate_item_id(cls, errors: List[str], zone_name: str,
                          item_id: int, context: str) -> None:
        """Validate an item ID."""
        if not (cls.MIN_ITEM_ID <= item_id <= cls.MAX_ITEM_ID):
            errors.append(f"Zone '{zone_name}' {context}: invalid item_id={item_id}")

    @classmethod
    def _parse_zone(cls, map_width: int, map_height: int,
                   zone: MapZone) -> Tuple[List[TileData], List[SpawnData], List[NPCSpawnData]]:
        """Parse a single zone into tiles and metadata lists."""
        tiles = []
        spawns = []
        npc_spawns = []

        cx = zone.center.get("x", 128)
        cy = zone.center.get("y", 128)
        r = zone.radius

        # Determine ground type for zone
        ground_id = cls._get_zone_ground(zone)
        z_level = 7 if zone.type != "dungeon" else 8

        # Fill zone area with ground
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    tx, ty = cx + dx, cy + dy
                    if 0 <= tx < map_width and 0 <= ty < map_height:
                        tiles.append(TileData(x=tx, y=ty, z=z_level, ground_id=ground_id))

        # Add buildings
        for building in zone.buildings:
            b_tiles = cls._parse_building(map_width, map_height, building, z_level)
            tiles.extend(b_tiles)

        # Add NPCs
        for npc in zone.npcs:
            npc_spawns.append(NPCSpawnData(
                x=npc.x, y=npc.y, z=npc.z, npc_name=npc.name,
            ))

        # Add spawns
        for spawn in zone.spawns:
            spawns.append(SpawnData(
                x=spawn.x, y=spawn.y, z=spawn.z,
                radius=spawn.radius,
                monsters=[(spawn.monster, 0, 0)],
            ))

        # Add dungeon rooms
        for room in zone.rooms:
            r_tiles = cls._parse_room(map_width, map_height, room)
            tiles.extend(r_tiles)

        return tiles, spawns, npc_spawns

    @classmethod
    def _get_zone_ground(cls, zone: MapZone) -> int:
        """Get the appropriate ground tile ID for a zone type."""
        ground_map = {
            "town": Tiles.STONE,
            "dungeon": Tiles.DIRT,
            "forest": Tiles.GRASS,
            "desert": Tiles.SAND,
            "lake": Tiles.WATER,
            "mountains": Tiles.ROCK,
        }
        if zone.ground_id > 0:
            return zone.ground_id
        return ground_map.get(zone.type, Tiles.GRASS)

    @classmethod
    def _parse_building(cls, map_width: int, map_height: int,
                       building: ZoneBuilding, z_level: int) -> List[TileData]:
        """Parse building tiles into a list."""
        tiles = []
        for tile_coords in building.tiles:
            if len(tile_coords) >= 2:
                x1, y1 = tile_coords[0], tile_coords[1]
                x2, y2 = tile_coords[0], tile_coords[1]
                if len(tile_coords) >= 4:
                    x2, y2 = tile_coords[2], tile_coords[3]

                for x in range(x1, x2 + 1):
                    for y in range(y1, y2 + 1):
                        if 0 <= x < map_width and 0 <= y < map_height:
                            # Place floor with wall item
                            tiles.append(TileData(
                                x=x, y=y, z=z_level,
                                ground_id=building.floor_id,
                                items=[ItemData(id=building.wall_id)],
                            ))
        # Place door on first tile
        if building.tiles and building.door_id > 0:
            first = building.tiles[0]
            if len(first) >= 2:
                tiles.append(TileData(
                    x=first[0], y=first[1], z=z_level,
                    ground_id=building.floor_id,
                    items=[ItemData(id=building.door_id)],
                ))
        return tiles

    @classmethod
    def _parse_room(cls, map_width: int, map_height: int,
                    room: ZoneRoom) -> List[TileData]:
        """Parse a dungeon room into tiles."""
        tiles = []
        for x in range(room.x, room.x + room.w):
            for y in range(room.y, room.y + room.h):
                if 0 <= x < map_width and 0 <= y < map_height:
                    tiles.append(TileData(x=x, y=y, z=room.z, ground_id=Tiles.DIRT))
        return tiles


# ═══════════════════════════════════════════════════════════════════════════
# MapComposer — Combines terrain base + LLM schema elements
# ═══════════════════════════════════════════════════════════════════════════

class MapComposer:
    """Combines a base terrain with LLM-generated zone elements."""

    @staticmethod
    def compose(schema: MapSchema, base_map: Optional[MapData] = None,
                seed: int = 42) -> MapData:
        """Compose a complete map from schema + optional terrain base.

        If base_map is provided, merge zone tiles on top of it.
        Otherwise, generate terrain from schema.terrain config.
        """
        w, h = schema.map_width, schema.map_height

        if base_map is None:
            # Generate terrain from schema config
            terrain_type = schema.terrain.get("type", "island")
            size = schema.terrain.get("size", w)
            base_map = MapComposer._generate_terrain(terrain_type, w, h, seed)

        # Parse schema zones into a partial map
        zone_map = SchemaParser.parse(schema)

        # Merge: zone tiles override terrain tiles at same position
        return MapComposer._merge(base_map, zone_map)

    @staticmethod
    def _generate_terrain(terrain_type: str, width: int, height: int,
                          seed: int) -> MapData:
        """Generate base terrain from terrain type string."""
        # Use TerrainGenerator for all types
        params = {"width": width, "height": height, "seed": seed}

        terrain_overrides = {
            "forest": {"water_level": 0.3},
            "desert": {"water_level": 0.0, "biome_scale": 0.01},
            "snow": {"water_level": 0.5},
            "mountain": {"water_level": 0.6, "biome_scale": 0.04},
            "swamp": {"water_level": 0.15},
        }

        for t_type, t_params in terrain_overrides.items():
            if t_type in terrain_type.lower():
                params.update(t_params)
                break

        gen = TerrainGenerator(**params)
        return gen.generate()

    @staticmethod
    def _merge(base: MapData, overlay: MapData) -> MapData:
        """Merge overlay on top of base (overlay wins for same tile)."""
        tile_map = {}

        # Add base tiles
        for tile in base.tiles:
            tile_map[(tile.x, tile.y, tile.z)] = tile

        # Overlay tiles from schema (they win)
        for tile in overlay.tiles:
            tile_map[(tile.x, tile.y, tile.z)] = tile

        # Combine items: if overlay tile has items and base had items at same pos, keep both
        for tile in overlay.tiles:
            key = (tile.x, tile.y, tile.z)
            if key in tile_map and tile_map[key] is not tile:
                # Merge items from base into overlay
                base_items = tile_map[key].items
                for item in base_items:
                    if item not in tile.items:
                        tile.items.append(item)

        all_tiles = list(tile_map.values())

        # Merge metadata from both
        all_towns = list(base.towns) + list(overlay.towns)
        all_waypoints = list(base.waypoints) + list(overlay.waypoints)
        all_spawns = list(base.spawns) + list(overlay.spawns)
        all_npc_spawns = list(base.npc_spawns) + list(overlay.npc_spawns)

        return MapData(
            width=max(base.width, overlay.width),
            height=max(base.height, overlay.height),
            description=overlay.description or base.description,
            tiles=all_tiles,
            towns=all_towns,
            waypoints=all_waypoints,
            spawns=all_spawns,
            npc_spawns=all_npc_spawns,
        )


# ═══════════════════════════════════════════════════════════════════════════
# LLMBridge — High-level API
# ═══════════════════════════════════════════════════════════════════════════

class LLMBridge:
    """High-level bridge: text prompt → MapData.

    Supports two modes:
    1. LLM-powered: sends prompt to LLM, gets JSON MapSchema, parses to MapData
    2. Pattern-based fallback: uses MapPromptParser if no LLM available

    Usage:
        bridge = LLMBridge(api_key="...", model="glm-5-turbo")
        map_data = bridge.generate_map("A tropical island with a pirate town")
    """

    def __init__(self, api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: str = "glm-5-turbo",
                 llm_client=None):
        """Initialize the bridge.

        Args:
            api_key: LLM API key (optional)
            base_url: LLM API base URL (optional)
            model: Model name (default: glm-5-turbo)
            llm_client: Optional custom LLM client function:
                        llm_client(system_prompt, user_prompt) -> str response
                        Useful for testing/mocking.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._llm_client = llm_client  # For testing/mocking

    def generate_map(self, prompt: str,
                     terrain: Optional[str] = None,
                     size: int = 256,
                     seed: int = 42,
                     base_map: Optional[MapData] = None) -> MapData:
        """Generate a map from a text prompt.

        Args:
            prompt: Natural language description
            terrain: Preferred terrain type (optional)
            size: Map size (default: 256)
            seed: Random seed (default: 42)
            base_map: Optional base terrain to build upon

        Returns:
            MapData instance
        """
        # Try LLM-powered generation
        if self._llm_client or (self.api_key and self.base_url):
            try:
                return self._generate_via_llm(prompt, terrain, size, seed, base_map)
            except Exception:
                pass  # Fall back to pattern-based

        # Fallback: pattern-based generation
        return self._generate_via_pattern(prompt, terrain, size, seed)

    def _generate_via_llm(self, prompt: str, terrain: Optional[str],
                          size: int, seed: int,
                          base_map: Optional[MapData]) -> MapData:
        """Generate map via LLM API."""
        system_prompt = PromptEngine.build_system_prompt()
        user_prompt = PromptEngine.build_user_prompt(prompt, terrain, size)

        if self._llm_client:
            response = self._llm_client(system_prompt, user_prompt)
        else:
            response = self._call_llm_api(system_prompt, user_prompt)

        # Parse JSON response
        schema = SchemaParser._parse_json_to_schema(response)

        # Override size if needed
        schema.map_width = size
        schema.map_height = size

        # Validate
        errors = SchemaParser.validate_schema(schema)
        if errors:
            raise ValueError(f"Schema validation errors: {errors}")

        # Compose final map
        return MapComposer.compose(schema, base_map=base_map, seed=seed)

    def _generate_via_pattern(self, prompt: str, terrain: Optional[str],
                              size: int, seed: int) -> MapData:
        """Fallback: use pattern-based parsing."""
        gen = LLMMapGenerator(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model,
        )
        return gen.generate(prompt, seed=seed)

    def _call_llm_api(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM API (OpenAI-compatible)."""
        import urllib.request
        import urllib.error

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(url, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        })

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════════════════
# Legacy classes — retained for backward compatibility
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GeneratorConfig:
    """Configuration for a single generator invocation."""
    generator: str  # "terrain", "dungeon", "city", "spawns"
    params: dict = field(default_factory=dict)
    offset_x: int = 0
    offset_y: int = 0


class MapPromptParser:
    """Parses natural language (Spanish/English) into generator configurations."""

    KEYWORDS = {
        "terrain": {
            "island": "island", "isla": "island",
            "map": "map", "mapa": "island",
            "terrain": "island", "terreno": "island",
            "bosque": "forest", "forest": "forest",
            "desert": "desert", "desierto": "desert",
            "nieve": "snow", "snow": "snow",
            "mountain": "mountain", "montaña": "mountain", "montana": "mountain",
            "river": "river", "rio": "river", "río": "river",
        },
        "dungeon": {
            "dungeon": "dungeon", "mazmorra": "dungeon", "cueva": "cave", "cave": "cave",
            "underground": "underground", "subterraneo": "underground",
            "catacombs": "catacombs", "catacumbas": "catacombs",
        },
        "city": {
            "city": "city", "ciudad": "city", "pueblo": "town", "town": "town",
            "village": "village", "aldea": "village", "villa": "villa",
            "castle": "castle", "castillo": "castle",
            "fortress": "fortress", "fortaleza": "fortress",
        },
        "spawns": {
            "spawn": "spawn", "monsters": "monsters", "monstruos": "monsters",
            "npc": "npc", "npcs": "npc", "characters": "characters",
        },
    }

    SIZE_PATTERNS = [
        re.compile(r'(\d+)\s*[x×]\s*(\d+)', re.IGNORECASE),
        re.compile(r'(\d+)\s*(?:de\s+)?ancho', re.IGNORECASE),
        re.compile(r'(\d+)\s*x?\s*(\d+)?', re.IGNORECASE),
    ]

    FLOOR_PATTERNS = re.compile(r'(\d+)\s*(?:pisos?|piso|floors?|levels?|niveles?)', re.IGNORECASE)
    ROOM_PATTERNS = re.compile(r'(\d+)\s*(?:rooms?|habitaciones?|salas?)', re.IGNORECASE)
    BUILDING_PATTERNS = re.compile(r'(\d+)\s*(?:buildings?|edificios?|casas?)', re.IGNORECASE)
    WALL_PATTERNS = re.compile(r'(?:amurallad[oa]|walled|murallas?|walls?)', re.IGNORECASE)
    SEED_PATTERNS = re.compile(r'seed[=:\s]*(\d+)', re.IGNORECASE)

    @classmethod
    def parse(cls, prompt: str, seed: Optional[int] = None) -> list:
        """Parse natural language prompt → list of GeneratorConfigs."""
        configs = []
        prompt_lower = prompt.lower()
        actual_seed = seed

        # Extract seed from prompt if not provided
        if actual_seed is None:
            m = cls.SEED_PATTERNS.search(prompt)
            if m:
                actual_seed = int(m.group(1))
            else:
                actual_seed = random.randint(0, 999999)

        # Extract common params
        size = cls._extract_size(prompt)
        floors = cls._extract_int(cls.FLOOR_PATTERNS, prompt, default=1)
        rooms = cls._extract_int(cls.ROOM_PATTERNS, prompt, default=8)
        buildings = cls._extract_int(cls.BUILDING_PATTERNS, prompt, default=12)
        has_walls = bool(cls.WALL_PATTERNS.search(prompt))
        width, height = size if size else (256, 256)

        # Detect which generators to use
        detected = set()

        for category, keywords in cls.KEYWORDS.items():
            for kw, variant in keywords.items():
                if kw in prompt_lower:
                    detected.add((category, variant))
                    break

        # Default: if nothing detected, generate an island
        if not detected:
            detected.add(("terrain", "island"))

        # Build configs
        offset_x = 0
        for category, variant in sorted(detected, key=lambda x: {"terrain": 0, "dungeon": 1, "city": 2, "spawns": 3}.get(x[0], 9)):
            if category == "terrain":
                params = {"seed": actual_seed, "width": width, "height": height}
                if variant == "forest":
                    params["water_level"] = 0.3
                elif variant == "desert":
                    params["water_level"] = 0.0
                    params["biome_scale"] = 0.01
                elif variant == "snow":
                    params["water_level"] = 0.5
                elif variant == "mountain":
                    params["water_level"] = 0.6
                    params["biome_scale"] = 0.04
                if "rio" in prompt_lower or "río" in prompt_lower or "river" in prompt_lower:
                    params["rivers"] = True
                configs.append(GeneratorConfig("terrain", params, offset_x, 0))
                offset_x += width

            elif category == "dungeon":
                dw, dh = min(width, 128), min(height, 128)
                params = {
                    "seed": actual_seed + 1, "width": dw, "height": dh,
                    "rooms_count": rooms, "floors": floors,
                }
                configs.append(GeneratorConfig("dungeon", params, offset_x, 0))
                offset_x += dw

            elif category == "city":
                cw, ch = min(width, 128), min(height, 128)
                params = {
                    "seed": actual_seed + 2, "width": cw, "height": ch,
                    "buildings_count": buildings, "has_walls": has_walls,
                }
                configs.append(GeneratorConfig("city", params, offset_x, 0))
                offset_x += cw

            elif category == "spawns":
                params = {"seed": actual_seed + 3, "density": 0.3}
                configs.append(GeneratorConfig("spawns", params, 0, 0))

        return configs

    @classmethod
    def _extract_size(cls, prompt: str) -> Optional[Tuple[int, int]]:
        for pattern in cls.SIZE_PATTERNS:
            m = pattern.search(prompt)
            if m:
                w = int(m.group(1))
                h = int(m.group(2)) if m.lastindex >= 2 and m.group(2) else w
                return (min(w, 2048), min(h, 2048))
        return None

    @classmethod
    def _extract_int(cls, pattern, prompt: str, default: int = 1) -> int:
        m = pattern.search(prompt)
        return int(m.group(1)) if m else default


class MapCombiner:
    """Combines multiple MapData instances into one."""

    @staticmethod
    def combine(*maps: MapData, mode: str = "overlay") -> MapData:
        """Combine multiple maps."""
        if not maps:
            return MapData(description="Empty combined map", width=256, height=256)

        if len(maps) == 1:
            return maps[0]

        if mode == "overlay":
            return MapCombiner._overlay(*maps)
        elif mode == "side_by_side":
            return MapCombiner._side_by_side(*maps)
        else:
            return MapCombiner._merge(*maps)

    @staticmethod
    def _overlay(*maps: MapData) -> MapData:
        """Stack maps at different z levels."""
        max_w = max(m.width for m in maps)
        max_h = max(m.height for m in maps)

        all_tiles = []
        all_towns = []
        all_waypoints = []
        all_spawns = []
        all_npc_spawns = []

        for i, m in enumerate(maps):
            z_offset = -i
            for tile in m.tiles:
                new_tile = TileData(
                    x=tile.x, y=tile.y, z=tile.z + z_offset,
                    ground_id=tile.ground_id, items=list(tile.items),
                    flags=tile.flags, house_id=tile.house_id,
                )
                all_tiles.append(new_tile)
            all_towns.extend(m.towns)
            all_waypoints.extend(m.waypoints)
            all_spawns.extend(m.spawns)
            all_npc_spawns.extend(m.npc_spawns)

        return MapData(
            description=f"Combined map ({len(maps)} layers)",
            width=max_w, height=max_h,
            tiles=all_tiles, towns=all_towns, waypoints=all_waypoints,
            spawns=all_spawns, npc_spawns=all_npc_spawns,
        )

    @staticmethod
    def _side_by_side(*maps: MapData) -> MapData:
        """Place maps next to each other horizontally."""
        total_width = sum(m.width for m in maps)
        max_height = max(m.height for m in maps)

        all_tiles = []
        all_towns = []
        all_waypoints = []
        all_spawns = []
        all_npc_spawns = []

        offset_x = 0
        for m in maps:
            for tile in m.tiles:
                new_tile = TileData(
                    x=tile.x + offset_x, y=tile.y, z=tile.z,
                    ground_id=tile.ground_id, items=list(tile.items),
                    flags=tile.flags, house_id=tile.house_id,
                )
                all_tiles.append(new_tile)
            for wp in m.waypoints:
                all_waypoints.append(wp)
            all_towns.extend(m.towns)
            all_spawns.extend(m.spawns)
            all_npc_spawns.extend(m.npc_spawns)
            offset_x += m.width

        return MapData(
            description=f"Combined map ({len(maps)} areas side-by-side)",
            width=total_width, height=max_height,
            tiles=all_tiles, towns=all_towns, waypoints=all_waypoints,
            spawns=all_spawns, npc_spawns=all_npc_spawns,
        )

    @staticmethod
    def _merge(*maps: MapData) -> MapData:
        """Merge all tiles into one map (later maps override earlier)."""
        tile_map = {}
        max_w, max_h = 256, 256

        for m in maps:
            max_w = max(max_w, m.width)
            max_h = max(max_h, m.height)
            for tile in m.tiles:
                key = (tile.x, tile.y, tile.z)
                tile_map[key] = tile

        all_towns = []
        all_waypoints = []
        all_spawns = []
        all_npc_spawns = []
        for m in maps:
            all_towns.extend(m.towns)
            all_waypoints.extend(m.waypoints)
            all_spawns.extend(m.spawns)
            all_npc_spawns.extend(m.npc_spawns)

        return MapData(
            description=f"Merged map ({len(maps)} sources)",
            width=max_w, height=max_h,
            tiles=list(tile_map.values()),
            towns=all_towns, waypoints=all_waypoints,
            spawns=all_spawns, npc_spawns=all_npc_spawns,
        )


class LLMMapGenerator:
    """Main entry: text prompt → MapData → optional OTBM file.

    Supports:
    1. Pure pattern parsing (no API needed)
    2. LLM-powered generation (OpenAI-compatible API)
    """

    GENERATOR_MAP = {
        "terrain": TerrainGenerator,
        "dungeon": DungeonGenerator,
        "city": CityGenerator,
        "spawns": SpawnGenerator,
    }

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "glm-5-turbo"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, output_file: Optional[str] = None, seed: Optional[int] = None) -> MapData:
        """Generate a map from text prompt."""
        # Step 1: Parse prompt into generator configs
        configs = MapPromptParser.parse(prompt, seed=seed)

        # Step 2: If API key available, try LLM enhancement
        if self.api_key and self.base_url:
            try:
                enhanced = self._llm_enhance(prompt, configs)
                if enhanced:
                    configs = enhanced
            except Exception:
                pass  # Fall back to pattern parsing

        # Step 3: Generate maps
        generated_maps = []
        for config in configs:
            generator_cls = self.GENERATOR_MAP.get(config.generator)
            if generator_cls:
                params = {k: v for k, v in config.params.items() if k in self._get_params(generator_cls)}
                if "seed" not in params:
                    params["seed"] = config.params.get("seed", random.randint(0, 999999))
                else:
                    params["seed"] = config.params.get("seed", random.randint(0, 999999))
                gen = generator_cls(**params)
                generated_maps.append(gen.generate())

        # Step 4: Combine maps
        if len(generated_maps) == 1:
            result = generated_maps[0]
        else:
            result = MapCombiner.combine(*generated_maps, mode="side_by_side")
            result.description = prompt

        # Step 5: Save if requested
        if output_file:
            from .otbm_writer import OTBMWriter
            writer = OTBMWriter(result)
            writer.save(output_file)

        return result

    def _llm_enhance(self, prompt: str, configs: list) -> Optional[list]:
        """Try to enhance generator configs using LLM."""
        try:
            import urllib.request
            import urllib.error

            system_prompt = """You are a Tibia map generation assistant. Given a user's map description,
output a JSON array of generator configurations. Each object has:
- "generator": one of "terrain", "dungeon", "city", "spawns"
- "params": object with generator-specific parameters

Available generators and params:
- terrain: seed, width, height, water_level (0-1), biome_scale (0.01-0.1), rivers (bool)
- dungeon: seed, width, height, rooms_count, min_room_size, max_room_size, floors
- city: seed, width, height, buildings_count, street_width, has_walls
- spawns: seed, density (0-1)

Respond ONLY with valid JSON array, no explanation."""

            url = f"{self.base_url.rstrip('/')}/chat/completions"
            payload = json.dumps({
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            }).encode()

            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            })

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                content = data["choices"][0]["message"]["content"]

            # Extract JSON from response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                enhanced = []
                for item in parsed:
                    gen = item.get("generator", "terrain")
                    params = item.get("params", {})
                    enhanced.append(GeneratorConfig(gen, params))
                return enhanced
        except Exception:
            pass
        return None

    @staticmethod
    def _get_params(cls) -> list:
        """Get parameter names from generator class __init__."""
        import inspect
        sig = inspect.signature(cls.__init__)
        return [p for p in sig.parameters if p != "self"]
