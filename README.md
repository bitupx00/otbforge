# Tibia AI Mapper

> AI-powered Tibia map editor — fork/extension of Remere's Map Editor: Redux

## Visión

Un map editor de Tibia (OTBM) donde la **IA (GLM-5-Turbo u otros LLMs)** puede:
1. **Generar mapas proceduralmente** — describir en texto lo que quieres y la IA lo crea
2. **Modificar zonas existentes** — "agrega una cueva de dragones al norte del castillo"
3. **Colocar spawns y NPCs** — la IA entiende la lógica del juego
4. **Bordes automáticos inteligentes** — la IA conoce las reglas de autoborder
5. **Exportar OTBM** — compatible con RME, OTClient, TFS/Canary

## Repos de Referencia

### Principal — RME Redux (nuestra base)
- **Repo:** `rme-redux/` — clone de https://github.com/TibiaDev/remeres-map-editor-redux
- C++23, OpenGL 4.x, wxWidgets 3.3, NanoVG
- ~900 commits, vibe-coded 90% con AI
- 160+ FPS renderer, async sprite loading
- OTBM read/write completo, OTB, DAT/SPR loading
- Arquitectura: `source/map/`, `source/brushes/`, `source/io/`, `source/rendering/`

### RME Original (OpenTibiaBR)
- **Repo:** `rme-source/` — clone de https://github.com/opentibiabr/remeres-map-editor
- Versión estable, C++ clásico, wxWidgets 2.9
- Referencia para formatos y compatibilidad

### OTBM Generator (Python)
- **Repo:** `otbm-gen/` — clone de https://github.com/Coldensjo/TibiaOTBMGenerator
- Perlin noise terrain generation → OTBM
- Buen punto de partida para generacion procedural

## Estructura del Proyecto

```
tibia-ai-mapper/
├── rme-redux/       # RME Redux source (base C++ editor)
├── rme-source/      # RME Original (referencia)
├── otbm-gen/        # Python OTBM generator (inspiración)
├── ai-core/         # [FUTURO] AI bridge — Python/Rust API
├── docs/            # Documentación
└── README.md
```

## Formatos Clave

### OTBM (OpenTibia Binary Map)
- Header: magic "OTBM" + version 2
- Nodes: TILE_AREA → TILE → ITEM
- Escaping: 0xFD before 0xFE/0xFF/0xFD
- Versiones soportadas: 2 (Tibia 7.6-8.x), 3 (Tibia 10+)

### DAT/SPR (Client Assets)
- DAT: item properties (flags, light, offset, etc.)
- SPR: sprite pixel data (32x32 tiles)
- Soporta versiones 7.x a 12.86+

### OTB (OpenTibia Binary Items)
- Items database en formato binario
- Versiones por cliente (8.0, 10.x, 12.x)

## Next Steps

1. Analizar el OTBM writer de RME Redux como base
2. Crear bridge Python ↔ OTBM (generación sin GUI)
3. Integrar LLM para descripción → tiles
4. Plugin system para comandos AI en RME
5. Web UI alternativa (Electron + WebGL)
