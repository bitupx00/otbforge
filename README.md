# OTBForge — OpenTibia AI Map Forge

> 🤖 AI-powered Tibia map generator. Describe un mapa en texto → obtiene un archivo OTBM listo para usar.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![Tests: 127](https://img.shields.io/badge/Tests-127%20passed-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()

## ✨ Features

- **🌐 Text → Map**: Describe en español o inglés lo que quieres y genera el mapa
- **🏔️ Terrain Generator**: Perlin noise con biomas, islas, ríos, vegetación automática
- **⚔️ Dungeon Generator**: BSP rooms + corridors, multi-piso, chests y stairs
- **🏘️ City Generator**: Grid streets, buildings, doors, NPCs, parks, murallas
- **👾 Spawn Generator**: 22 tipos de monstruos con colocación bioma-aware
- **🧠 LLM Bridge**: Compatible con GLM-5-Turbo, OpenAI, Ollama (opcional)
- **📦 OTBM v2**: Writer + Reader completos con roundtrip verificado
- **✅ Map Validator**: 13 checks de integridad (bounds, duplicates, IDs, etc)
- **🔧 Zero Dependencies**: Solo Python stdlib, nada de numpy o similares

## 🚀 Quick Start

```bash
# Generar una isla con ciudad
python3 -m ai_core.cli gen "una isla 256x256 con bosque y ciudad amurallada" -o mi_mapa.otbm

# Generar un dungeon de 3 pisos
python3 -m ai_core.cli gen "dungeon de 3 pisos con 10 habitaciones" -o dungeon.otbm --seed 42

# Ver info de un mapa
python3 -m ai_core.cli info mi_mapa.otbm
```

## 🎮 Comandos

```bash
python3 -m ai_core.cli gen "descripción del mapa" -o output.otbm [opciones]
python3 -m ai_core.cli info archivo.otbm
```

### Opciones
| Flag | Descripción | Default |
|------|-------------|---------|
| `-o, --output` | Archivo OTBM de salida | `output.otbm` |
| `--seed` | Semilla aleatoria | Auto |
| `--api-key` | API key para LLM (opcional) | None |
| `--api-url` | Base URL del LLM (opcional) | None |
| `--model` | Modelo LLM | `glm-5-turbo` |

## 🧠 LLM Integration (Opcional)

Sin API key, funciona con **pattern parsing** puro. Con API:

```bash
python3 -m ai_core.cli gen "un castillo fortificado con mazmorra subterránea y dragones" \
  --api-key TU_KEY --api-url https://api.example.com/v1 --model glm-5-turbo \
  -o castle.otbm
```

Compatible con cualquier API OpenAI-compatible: GLM-5-Turbo, GPT-4, Claude (via proxy), Ollama local.

## 🏗️ Architecture

```
ai_core/
├── __init__.py          # Package exports
├── otbm_types.py        # Dataclasses + OTBM constants
├── otbm_writer.py       # MapData → OTBM binary
├── otbm_reader.py       # OTBM binary → MapData
├── llm_bridge.py        # Text → MapData (parser + LLM + combiner)
├── map_validator.py     # 13 integrity checks
├── cli.py               # CLI interface
└── generators/
    ├── terrain.py       # Perlin noise terrain
    ├── dungeon.py       # BSP dungeon
    ├── city.py          # Grid city
    └── spawns.py        # Monster/NPC spawns
```

## 📊 Test Coverage

```
127 tests — all passing in <10s

tests/test_otbm.py         35  — OTBM writer/reader roundtrip
tests/test_generators.py  37  — Terrain/Dungeon/City/Spawn generators
tests/test_llm_bridge.py   24  — Prompt parser + combiner + LLM
tests/test_validator.py    31  — Map integrity validation
```

## 🔧 Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Generate a test map
python3 -m ai_core.cli gen "isla 64x64" -o test.otbm --seed 42

# Validate a map
python3 -c "from ai_core.map_validator import MapValidator; from ai_core.otbm_reader import OTBMReader; m=OTBMReader(open('test.otbm','rb').read()).read(); issues=MapValidator.validate(m); print(MapValidator.summary(issues))"
```

## 📋 Supported Map Elements

- ✅ Ground tiles (grass, dirt, sand, water, snow, rock, lava)
- ✅ Items stacked on tiles (containers, chests, teleporters)
- ✅ Tile flags (protection zone, PvP zone, house tiles)
- ✅ Towns with temple positions
- ✅ Waypoints
- ✅ Monster spawns (22 types: dragon, demon, orc, spider, vampire...)
- ✅ NPC spawns (Merchant, Banker, Healer, Guild Leader...)
- ✅ Houses with doors
- ✅ Nested containers (chest → drawer → items)

## 🎯 Roadmap

- [ ] OTB DAT/SPR loader (sprite assets)
- [ ] Web UI (React + WebGL map viewer)
- [ ] RME plugin integration
- [ ] Multi-biome advanced generation
- [ ] Quest/area designer
- [ ] OTMM format support (Tibia 10+)
- [ ] Import/export to other formats (JSON, XML)

## 📜 License

MIT — Free for OpenTibia community.

## 🙏 Credits

- Based on [Remere's Map Editor: Redux](https://github.com/TibiaDev/remeres-map-editor-redux) (C++23, 90% AI-coded)
- OTBM format reference from [OpenTibiaBR RME](https://github.com/opentibiabr/remeres-map-editor)
- Inspiration from [TibiaOTBMGenerator](https://github.com/Coldensjo/TibiaOTBMGenerator)
