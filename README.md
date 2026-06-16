<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Tests-492%20passed-brightgreen.svg" alt="Tests">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/Zero%20Dependencies-stdlib%20only-success.svg" alt="Zero Dependencies">
  <img src="https://img.shields.io/badge/OTBM-v2%20%2F%20v3-informational.svg" alt="OTBM v2/v3">
</p>

<h1 align="center">⚒️ OTBForge — OpenTibia AI Map Forge</h1>

<p align="center">
  <strong>AI-powered Tibia map generator.</strong><br>
  Describe a map in text → get a production-ready <code>.otbm</code> file.<br>
  Works with or without an LLM — pure pattern parsing fallback included.
</p>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🌍 **Terrain Generator** | Multi-octave Perlin noise with 11 biomes, rivers, island shaping |
| 🏰 **Dungeon Generator** | BSP room partitioning, 5 room types, multi-floor, corridors & chests |
| 🏘️ **Town Generator** | Grid / radial / random layouts, 3 architectural styles, NPCs |
| 🏠 **House Placer** | Rectangular houses with walls, doors, furniture, house IDs |
| 🛤️ **Road Generator** | A\* pathfinding with bridge support, configurable width |
| 💧 **Water Features** | Lakes, wells, oases, fountains, waterfalls |
| 🌿 **Vegetation** | Clustered trees, flower patches, hedge rows, biome-aware |
| 👾 **Spawn Manager** | 24 monster types + 11 NPCs, biome-aware placement, safety zones |
| 🧩 **Compositor** | Full pipeline orchestrator — terrain → roads → towns → spawns → houses → vegetation → water |
| 🤖 **LLM Bridge** | Text prompt → structured JSON → MapData. Works offline with pattern parsing |
| 📦 **OTBM Writer/Reader** | Full v2/v3 binary read + write with verified roundtrip |
| ✅ **Map Validator** | Integrity checks (bounds, duplicates, IDs, nesting, towns, spawns) |
| 🔁 **Format Converter** | OTBM ↔ JSON bidirectional conversion |

---

## 🚀 Installation

```bash
# Clone
git clone https://github.com/bitupx00/otbforge.git
cd otbforge

# Install (user-level, no venv needed — zero external dependencies)
pip install --user .

# Or just run directly from source
export PYTHONPATH=/home/bitupx/otbforge:$PYTHONPATH
```

> **Requirements:** Python 3.11+. No numpy, no external packages — pure stdlib.

---

## 🎮 CLI Usage

### Generate terrain

```bash
python3 -m ai_core.cli generate terrain --size 256 --seed 42 --output island.otbm
python3 -m ai_core.cli generate terrain --size 128 --biome mountain --water-level 0.3 -o mountain.otbm
```

| Flag | Description | Default |
|------|-------------|---------|
| `--size, -s` | Map size (NxN) | `256` |
| `--seed` | Random seed | `42` |
| `--water-level` | Water level threshold (0–1) | auto |
| `--biome` | Biome hint: `plains`, `forest`, `mountain`, `desert`, `snow` | auto |
| `--output, -o` | Output file | `terrain.otbm` |

### Generate dungeon

```bash
python3 -m ai_core.cli generate dungeon --rooms 10 --floors 3 --size 50 --output dungeon.otbm
```

| Flag | Description | Default |
|------|-------------|---------|
| `--size, -s` | Map size (NxN) | `50` |
| `--rooms, -r` | Number of rooms | `8` |
| `--floors, -f` | Number of floors | `1` |
| `--seed` | Random seed | `42` |
| `--output, -o` | Output file | `dungeon.otbm` |

### Generate via AI

```bash
# Offline (pattern parsing — no API key needed)
python3 -m ai_core.cli generate ai --prompt "isla tropical con pueblo pirata" -o pirate.otbm

# With LLM API
python3 -m ai_core.cli generate ai \
  --prompt "a fortified castle with underground dungeon and dragons" \
  --api-key YOUR_KEY --api-url https://api.example.com/v1 --model glm-5-turbo \
  -o castle.otbm
```

| Flag | Description | Default |
|------|-------------|---------|
| `prompt` | Text description of the map | *(required)* |
| `--seed` | Random seed | auto |
| `--api-key` | LLM API key | None (offline mode) |
| `--api-url` | LLM API base URL | None |
| `--model` | LLM model name | `glm-5-turbo` |
| `--output, -o` | Output file | `ai_map.otbm` |

> Compatible with any OpenAI-compatible API: GLM-5-Turbo, GPT-4, Claude (via proxy), Ollama local.

### Validate a map

```bash
python3 -m ai_core.cli validate map.otbm
```

### Inspect a map

```bash
python3 -m ai_core.cli info map.otbm
```

Output includes: map size, OTBM version, tile count, z-levels, ground type distribution, towns, waypoints, spawns, NPCs.

### Convert formats

```bash
# OTBM → JSON
python3 -m ai_core.cli convert map.otbm --format json --output map.json

# JSON → OTBM
python3 -m ai_core.cli convert map.json --format otbm --output map.otbm
```

### Shorthand aliases

Every command supports short aliases:

```bash
python3 -m ai_core.cli gen t --size 128 -o terrain.otbm    # generate terrain
python3 -m ai_core.cli gen d --rooms 15 -o dungeon.otbm     # generate dungeon
python3 -m ai_core.cli gen a --prompt "forest" -o forest.otbm  # generate ai
python3 -m ai_core.cli v map.otbm                            # validate
python3 -m ai_core.cli i map.otbm                            # info
python3 -m ai_core.cli c map.otbm -f json                    # convert
```

---

## 🐍 Python API

### Terrain

```python
from ai_core.generators.terrain import TerrainGenerator

gen = TerrainGenerator(width=256, height=256, seed=42, water_level=0.35)
map_data = gen.generate()
# map_data.tiles, map_data.towns, map_data.spawns ...
```

### Dungeon

```python
from ai_core.generators.dungeon import DungeonGenerator

gen = DungeonGenerator(width=50, height=50, rooms_count=10, seed=42)
map_data = gen.generate()
```

### Town

```python
from ai_core.generators.town import TownGenerator

gen = TownGenerator(
    width=80, height=80, seed=42,
    layout="grid",       # "grid" | "radial" | "random"
    style="medieval",    # "medieval" | "tropical" | "winter"
)
map_data = gen.generate()
```

### Full Pipeline (Compositor)

```python
from ai_core.generators.compositor import FullMapGenerator, CompositorConfig

config = CompositorConfig(
    width=512, height=512, seed=42,
    num_towns=3,
    num_spawn_zones=5,
    road_width=2,
    enable_vegetation=True,
    enable_water_features=True,
)
gen = FullMapGenerator(config)
map_data = gen.generate()

# Write to OTBM
from ai_core.otbm_writer import OTBMWriter
OTBMWriter(map_data).save("full_map.otbm")
```

The compositor orchestrates the full pipeline:
`terrain → roads → towns → spawns → houses → vegetation → water features`

Each stage can be enabled/disabled and configured independently via `CompositorConfig`.

### LLM Bridge

```python
from ai_core.llm_bridge import LLMBridge

bridge = LLMBridge(api_key="your-key", model="glm-5-turbo")
map_data = bridge.generate_map("A tropical island with a pirate town and dragon cave")
```

For offline / no-API usage, the `LLMMapGenerator` falls back to pattern-based parsing:

```python
from ai_core.llm_bridge import LLMMapGenerator

gen = LLMMapGenerator()  # no API key → offline mode
map_data = gen.generate("una isla con bosque y ciudad amurallada", output_file="isla.otbm")
```

### Read / Write / Validate OTBM

```python
from ai_core.otbm_reader import OTBMReader
from ai_core.otbm_writer import OTBMWriter
from ai_core.map_validator import MapValidator

# Read
with open("map.otbm", "rb") as f:
    map_data = OTBMReader(data=f.read()).read()

# Write
OTBMWriter(map_data).save("output.otbm")

# Validate
issues = MapValidator.validate(map_data)
summary = MapValidator.summary(issues)
print(f"Errors: {summary['errors']}, Warnings: {summary['warnings']}, Info: {summary['info']}")
```

---

## 🏗️ Architecture

```
ai_core/
├── __init__.py              # Package exports (Position, MapData, OTBMWriter, …)
├── models.py                # Data models, constants, enums
├── otbm_types.py            # OTBM node types, attribute types, backward-compat aliases
├── otbm_writer.py           # MapData → .otbm binary (OTBM v2/v3)
├── otbm_reader.py           # .otbm binary → MapData
├── map_validator.py         # Integrity validation (bounds, duplicates, IDs, nesting)
├── llm_bridge.py            # LLM integration (PromptEngine → SchemaParser → MapComposer → LLMBridge)
├── cli.py                   # CLI interface (generate / validate / info / convert)
└── generators/
    ├── __init__.py           # Generator exports
    ├── terrain.py            # Perlin noise terrain (11 biomes, rivers, island shaping)
    ├── dungeon.py            # BSP dungeon (5 room types, multi-floor, corridors)
    ├── town.py               # Town/city generator (grid/radial/random, 3 styles)
    ├── spawn_manager.py      # Biome-aware monster & NPC placement (24 + 11 types)
    ├── house_placer.py       # House rectangles with walls, doors, furniture
    ├── road_generator.py     # A* pathfinding roads with bridges
    ├── water_features.py     # Lakes, wells, oases, fountains, waterfalls
    ├── vegetation.py        # Clustered trees, flowers, hedges
    └── compositor.py         # Full pipeline orchestrator (CompositorConfig → FullMapGenerator)
```

### LLM Bridge Architecture

```
Text Prompt
    │
    ├── [Offline] PatternParser → MapSchema (structured dict)
    │                                    │
    └── [Online]  PromptEngine → LLM API → JSON → SchemaParser
                                             │
                                      MapComposer
                                             │
                                         MapData
                                             │
                                         OTBMWriter
                                             │
                                          .otbm file
```

The bridge has two modes:
- **Online (LLM):** `PromptEngine` builds a structured prompt → LLM returns JSON → `SchemaParser` validates and converts → `MapComposer` places elements on a terrain base.
- **Offline (Pattern):** `MapPromptParser` extracts entities via regex patterns → `MapCombiner` assembles the map — no API needed.

---

## 🔧 Generators Reference

| Generator | Class | Key Parameters |
|-----------|-------|-----------------|
| Terrain | `TerrainGenerator` | `width`, `height`, `seed`, `water_level`, `biome_scale` |
| Dungeon | `DungeonGenerator` | `width`, `height`, `rooms_count`, `seed` |
| Town | `TownGenerator` | `width`, `height`, `seed`, `layout`, `style` |
| Houses | `HousePlacer` | `map_data`, `town_positions`, `seed`, `houses_per_town` |
| Roads | `RoadGenerator` | `map_data`, `waypoints`, `width`, `seed` |
| Water | `WaterFeatureGenerator` | `map_data`, `seed`, `num_lakes`, `num_wells` |
| Vegetation | `VegetationEnhancer` | `map_data`, `seed`, `density`, `cluster_count` |
| Spawns | `SpawnManager` | `map_data`, `seed`, `monster_density`, `npc_types` |
| **Full Pipeline** | `FullMapGenerator` | `CompositorConfig(width, height, seed, num_towns, …)` |

### Biomes (Terrain)

Plains, Forest, Swamp, Desert, Hills, Mountains, Snow, Tundra, Jungle, Volcanic, Water — selected automatically by elevation + moisture noise.

### Room Types (Dungeon)

Normal, Treasure (chests), Boss (high-value loot), Spawn (monster spawn points), Trap (damage tiles).

### Town Styles

- **Medieval** — Stone walls, wood floors, cobblestone streets
- **Tropical** — Sand walls, palm trees, sandy paths
- **Winter** — Ice walls, snow floors, frosted stone

### Monster Database (24 types)

Rat, Snake, Spider, Orc, Wolf, Dwarf, Troll, Cyclops, Minotaur, Dragon, Demon, Vampire, Skeleton, Zombie, Ghost, Fire Elemental, Earth Elemental, Necromancer, Warlock, Hunter, Amazon, Pirate, Lizardman, Scorpion.

### NPC Types (11)

Merchant, Banker, Healer, Guild Leader, Blacksmith, Alchemist, Tavern Keeper, Boat Captain, Hunter Guild, Mage Guild, Royal Advisor.

---

## ✅ Testing

**492 tests** covering every module — all passing.

```bash
cd otbforge
python3 -m pytest tests/ -v
```

### Test Breakdown

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_roundtrip.py` | 84 | OTBM writer/reader binary roundtrip |
| `test_validator.py` | 127 | Map integrity validation |
| `test_terrain.py` | 42 | Terrain generation (biomes, rivers, islands) |
| `test_dungeon.py` | 42 | Dungeon BSP generation |
| `test_generators.py` | 3 | Legacy generator tests |
| `test_llm_bridge.py` | 45 | LLM bridge (prompt parsing, schema, composer) |
| `test_cli.py` | 33 | CLI commands |
| `test_town.py` | 28 | Town generation (layouts, styles) |
| `test_spawn.py` | 30 | Spawn placement (monsters, NPCs, biomes) |
| `test_house.py` | 27 | House placement (walls, doors, furniture) |
| `test_road.py` | 15 | A\* roads & bridges |
| `test_water.py` | 12 | Water features |
| `test_vegetation.py` | 13 | Vegetation clustering |
| `test_compositor.py` | 18 | Full pipeline compositor |

---

## 🤝 Contributing

Contributions are welcome! This is an open-source project for the OpenTibia community.

### Quick Start

```bash
git clone https://github.com/bitupx00/otbforge.git
cd otbforge
python3 -m pytest tests/ -v          # verify all tests pass
```

### Guidelines

1. **Write tests.** All new features must include tests. Run the full suite before pushing:
   ```bash
   python3 -m pytest tests/ -v
   ```

2. **Zero dependencies.** This project uses only Python stdlib. Do not add external packages.

3. **OTBM accuracy.** Any changes to the writer/reader must pass roundtrip tests (write → read → write → compare).

4. **Code style.** Follow the existing conventions — type hints, docstrings on modules/classes, clean imports.

5. **Commits.** Use clear, descriptive commit messages. Reference issue numbers when applicable.

### Project Structure for New Generators

To add a new generator:

1. Create `ai_core/generators/your_generator.py` with a class that produces `MapData`.
2. Add imports to `ai_core/generators/__init__.py`.
3. Add CLI subcommand in `ai_core/cli.py`.
4. Add tests in `tests/test_your_generator.py`.
5. Wire into the compositor if it's a pipeline stage (update `CompositorConfig` and `FullMapGenerator`).

---

## 🗺️ Supported Map Elements

- ✅ Ground tiles (grass, dirt, sand, water, snow, rock, lava, swamp, jungle)
- ✅ Items stacked on tiles (containers, chests, teleporters, decorations)
- ✅ Tile flags (protection zone, PvP zone, no logout, house tiles)
- ✅ Towns with temple positions
- ✅ Waypoints
- ✅ Monster spawns (24 types, biome-aware)
- ✅ NPC spawns (11 types)
- ✅ Houses with doors and house IDs
- ✅ Nested containers (chest → drawer → items)
- ✅ Multi-floor maps (z-levels)
- ✅ Roads, bridges, and path networks
- ✅ Water features (lakes, wells, oases, fountains)

---

## 🎯 Roadmap

- [ ] OTB DAT/SPR loader (sprite assets)
- [ ] Web UI (React + WebGL map viewer)
- [ ] RME plugin integration
- [ ] Quest/area designer
- [ ] OTMM format support (Tibia 10+)
- [ ] Import/export extended formats (XML, Tiled TMX)

---

## 📜 License

MIT — Free and open for the OpenTibia community.

---

## 🙏 Credits

- Based on [Remere's Map Editor: Redux](https://github.com/TibiaDev/remeres-map-editor-redux) (C++23, 90% AI-coded)
- OTBM format reference from [OpenTibiaBR RME](https://github.com/opentibiabr/remeres-map-editor)
- Inspiration from [TibiaOTBMGenerator](https://github.com/Coldensjo/TibiaOTBMGenerator)
