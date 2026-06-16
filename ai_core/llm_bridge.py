"""LLM Bridge — Text prompt → Map generation via pattern parsing + optional LLM API."""

import json
import re
import random
from dataclasses import dataclass, field
from typing import Optional
from ai_core.generators import TerrainGenerator, DungeonGenerator, CityGenerator, SpawnGenerator
from ai_core.otbm_types import MapData, TileData


@dataclass
class GeneratorConfig:
    """Configuration for a single generator invocation."""
    generator: str  # "terrain", "dungeon", "city", "spawns"
    params: dict = field(default_factory=dict)
    offset_x: int = 0
    offset_y: int = 0


# ─── MapPromptParser ────────────────────────────────────────────────────

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
    def parse(cls, prompt: str, seed: Optional[int] = None) -> list[GeneratorConfig]:
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
                # Spawns layer on top of existing maps
                params = {"seed": actual_seed + 3, "density": 0.3}
                configs.append(GeneratorConfig("spawns", params, 0, 0))

        return configs

    @classmethod
    def _extract_size(cls, prompt: str) -> Optional[tuple[int, int]]:
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


# Fix: detected_as_list is not defined, use prompt_lower for river check
# This is handled inline above with direct prompt_lower check

# ─── MapCombiner ────────────────────────────────────────────────────────

class MapCombiner:
    """Combines multiple MapData instances into one."""

    @staticmethod
    def combine(*maps: MapData, mode: str = "overlay") -> MapData:
        """Combine multiple maps.

        Modes:
            overlay: place maps at different z levels (terrain z=0, dungeon z=-1, etc.)
            side_by_side: place maps next to each other (offset x)
            merge: merge all tiles into one map, with offset support
        """
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
            z_offset = -i  # First map at z=0, second at z=-1, etc.
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
                tile_map[key] = tile  # Last write wins

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


# ─── LLMMapGenerator ────────────────────────────────────────────────────

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
        """Generate a map from text prompt.

        Args:
            prompt: Natural language description (Spanish/English)
            output_file: Optional path to save .otbm file
            seed: Optional random seed (auto-generated if not provided)

        Returns:
            MapData instance
        """
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
                params = {k: v for k, v in config.params.items() if k != "seed" and k in self._get_params(generator_cls)}
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

    def _llm_enhance(self, prompt: str, configs: list[GeneratorConfig]) -> Optional[list[GeneratorConfig]]:
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
    def _get_params(cls) -> list[str]:
        """Get parameter names from generator class __init__."""
        import inspect
        sig = inspect.signature(cls.__init__)
        return [p for p in sig.parameters if p != "self"]
