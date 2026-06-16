#!/usr/bin/env python3
"""OTBForge CLI — Generate, validate, inspect, and convert Tibia OTBM maps.

Usage:
    otbforge generate terrain --size 256 --seed 42 --output island.otbm
    otbforge generate dungeon --rooms 10 --floors 3 --output dungeon.otbm
    otbforge generate ai --prompt "castillo con cueva" --output castle.otbm
    otbforge validate map.otbm
    otbforge info map.otbm
    otbforge convert map.otbm --format json --output map.json
    otbforge convert map.json --format otbm --output map.otbm
"""

import argparse
import json
import sys
import time
import os

# Add parent dir to path for -m execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_map(filepath: str):
    """Load a MapData from OTBM or JSON file."""
    from ai_core.otbm_reader import OTBMReader

    if filepath.endswith(".json"):
        return _load_json_map(filepath)

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    with open(filepath, "rb") as f:
        data = f.read()
    reader = OTBMReader(data=data)
    return reader.read()


def _load_json_map(filepath: str):
    """Load a MapData from JSON file."""
    from ai_core.otbm_types import (
        MapData, TileData, TownData, WaypointData,
        SpawnData, NPCSpawnData, Position,
    )

    with open(filepath, "r") as f:
        data = json.load(f)

    tiles = []
    for t_data in data.get("tiles", []):
        items = []
        for i_data in t_data.get("items", []):
            items.append(__import__('ai_core.otbm_types', fromlist=['ItemData']).ItemData(
                id=i_data["id"],
                count=i_data.get("count", 0),
                action_id=i_data.get("action_id", 0),
            ))
        tile = TileData(
            x=t_data["x"], y=t_data["y"], z=t_data["z"],
            ground_id=t_data.get("ground_id", 0),
            items=items,
            flags=t_data.get("flags", 0),
            house_id=t_data.get("house_id", 0),
        )
        tiles.append(tile)

    towns = []
    for tw in data.get("towns", []):
        temple = tw.get("temple", {})
        if isinstance(temple, (list, tuple)):
            tp = Position(x=temple[0], y=temple[1], z=temple[2] if len(temple) > 2 else 7)
        else:
            tp = Position(**temple)
        towns.append(TownData(id=tw["id"], name=tw["name"], temple=tp))

    waypoints = [WaypointData(name=wp["name"], pos=Position(**wp["pos"])) for wp in data.get("waypoints", [])]
    spawns = [SpawnData(x=s["x"], y=s["y"], z=s["z"], radius=s.get("radius", 0)) for s in data.get("spawns", [])]
    npc_spawns = [NPCSpawnData(x=n["x"], y=n["y"], z=n["z"], npc_name=n.get("npc_name", "")) for n in data.get("npc_spawns", [])]

    return MapData(
        width=data.get("width", 2048),
        height=data.get("height", 2048),
        description=data.get("description", "Imported Map"),
        tiles=tiles,
        towns=towns,
        waypoints=waypoints,
        spawns=spawns,
        npc_spawns=npc_spawns,
    )


def _map_to_json(map_data) -> dict:
    """Serialize MapData to JSON-compatible dict."""
    tiles = []
    for t in map_data.tiles:
        items = []
        for item in t.items:
            items.append({"id": item.id, "count": item.count, "action_id": item.action_id})
        tiles.append({
            "x": t.x, "y": t.y, "z": t.z,
            "ground_id": t.ground_id,
            "flags": int(t.flags) if hasattr(t.flags, 'value') else t.flags,
            "house_id": t.house_id,
            "items": items,
        })

    towns = []
    for tw in map_data.towns:
        tp = tw.temple
        towns.append({
            "id": tw.id, "name": tw.name,
            "temple": {"x": tp.x, "y": tp.y, "z": tp.z},
        })

    waypoints = [{"name": wp.name, "pos": {"x": wp.pos.x, "y": wp.pos.y, "z": wp.pos.z}} for wp in map_data.waypoints]
    spawns = [{"x": s.x, "y": s.y, "z": s.z, "radius": s.radius} for s in map_data.spawns]
    npc_spawns = [{"x": n.x, "y": n.y, "z": n.z, "npc_name": n.npc_name} for n in map_data.npc_spawns]

    return {
        "width": map_data.width,
        "height": map_data.height,
        "description": map_data.description,
        "otbm_version": map_data.otbm_version,
        "tiles": tiles,
        "towns": towns,
        "waypoints": waypoints,
        "spawns": spawns,
        "npc_spawns": npc_spawns,
    }


def _save_json(map_data, filepath: str):
    """Save MapData as JSON."""
    data = _map_to_json(map_data)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def _save_otbm(map_data, filepath: str):
    """Save MapData as OTBM."""
    from ai_core.otbm_writer import OTBMWriter
    writer = OTBMWriter(map_data)
    writer.save(filepath)


# ═══════════════════════════════════════════════════════════════════════════
# Subcommands
# ═══════════════════════════════════════════════════════════════════════════

def cmd_generate_terrain(args):
    """Generate terrain map."""
    from ai_core.generators.terrain import TerrainGenerator

    size = args.size
    seed = args.seed if args.seed is not None else 42
    print(f"🌍 Generating terrain ({size}x{size}, seed={seed})...")
    start = time.time()

    params = {"width": size, "height": size, "seed": seed}
    if args.water_level is not None:
        params["water_level"] = args.water_level
    if args.biome:
        params["biome_scale"] = {"plains": 0.02, "forest": 0.03, "mountain": 0.04,
                                  "desert": 0.01, "snow": 0.02}.get(args.biome, 0.02)

    gen = TerrainGenerator(**params)
    result = gen.generate()

    _save_otbm(result, args.output)

    elapsed = time.time() - start
    print(f"✅ Terrain generated in {elapsed:.2f}s")
    print(f"   Tiles: {len(result.tiles):,}")
    print(f"   File: {args.output} ({os.path.getsize(args.output):,} bytes)")
    return 0


def cmd_generate_dungeon(args):
    """Generate dungeon map."""
    from ai_core.generators.dungeon import DungeonGenerator

    size = args.size
    rooms = args.rooms
    floors = args.floors
    seed = args.seed if args.seed is not None else 42
    print(f"🏰 Generating dungeon ({size}x{size}, {rooms} rooms, {floors} floors, seed={seed})...")
    start = time.time()

    gen = DungeonGenerator(width=size, height=size, rooms_count=rooms, seed=seed)
    result = gen.generate()

    _save_otbm(result, args.output)

    elapsed = time.time() - start
    print(f"✅ Dungeon generated in {elapsed:.2f}s")
    print(f"   Tiles: {len(result.tiles):,}")
    print(f"   File: {args.output} ({os.path.getsize(args.output):,} bytes)")
    return 0


def cmd_generate_ai(args):
    """Generate map via AI/LLM."""
    from ai_core.llm_bridge import LLMMapGenerator

    prompt = args.prompt
    seed = args.seed if args.seed is not None else None
    print(f"🤖 Generating map from: '{prompt}'")
    start = time.time()

    gen = LLMMapGenerator(
        api_key=args.api_key,
        base_url=args.api_url,
        model=args.model,
    )
    result = gen.generate(prompt, output_file=args.output, seed=seed)

    elapsed = time.time() - start
    tile_count = len(result.tiles)
    file_size = os.path.getsize(args.output) if os.path.exists(args.output) else 0

    print(f"✅ Map generated in {elapsed:.2f}s")
    print(f"   Tiles: {tile_count:,}")
    print(f"   Towns: {len(result.towns)}")
    print(f"   Waypoints: {len(result.waypoints)}")
    print(f"   Spawns: {len(result.spawns)}")
    print(f"   NPCs: {len(result.npc_spawns)}")
    if file_size > 0:
        print(f"   File: {args.output} ({file_size:,} bytes)")
    return 0


def cmd_validate(args):
    """Validate an OTBM file."""
    from ai_core.map_validator import MapValidator

    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        return 1

    try:
        map_data = _load_map(filepath)
    except Exception as e:
        print(f"❌ Failed to read file: {e}", file=sys.stderr)
        return 1

    issues = MapValidator.validate(map_data)
    summary = MapValidator.summary(issues)

    if not issues:
        print(f"✅ {filepath}: Valid (0 issues)")
        return 0

    print(f"🔍 {filepath}: {summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info")
    for issue in issues:
        severity_icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue.severity, "•")
        pos = f" at {issue.position}" if issue.position else ""
        print(f"  {severity_icon} [{issue.severity}] {issue.category}: {issue.message}{pos}")

    return 1 if summary["errors"] > 0 else 0


def cmd_info(args):
    """Display info about an OTBM or JSON file."""
    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        return 1

    try:
        map_data = _load_map(filepath)
    except Exception as e:
        print(f"❌ Failed to read file: {e}", file=sys.stderr)
        return 1

    print(f"🗺️  Map: {map_data.description}")
    print(f"   Size: {map_data.width}x{map_data.height}")
    print(f"   OTBM Version: {map_data.otbm_version}")
    print(f"   Tiles: {len(map_data.tiles):,}")

    # Count by z-level
    z_levels = {}
    for tile in map_data.tiles:
        z = tile.z
        z_levels[z] = z_levels.get(z, 0) + 1
    if z_levels:
        print(f"   Z-levels: {dict(sorted(z_levels.items()))}")

    # Ground type distribution
    ground_types = {}
    for tile in map_data.tiles:
        g = tile.ground_id
        ground_types[g] = ground_types.get(g, 0) + 1
    top_grounds = sorted(ground_types.items(), key=lambda x: -x[1])[:10]
    if top_grounds:
        print(f"   Top ground types: {[(f'0x{g:04X}', c) for g, c in top_grounds]}")

    # Stats
    stats = map_data.stats() if hasattr(map_data, 'stats') else {}
    if stats:
        print(f"   Ground tiles: {stats.get('ground_tiles', '?')}")
        print(f"   Items: {stats.get('total_items', '?')}")
        print(f"   House tiles: {stats.get('house_tiles', '?')}")

    print(f"   Towns: {len(map_data.towns)}")
    for town in map_data.towns:
        print(f"      - {town.name} (ID {town.id})")
    print(f"   Waypoints: {len(map_data.waypoints)}")
    for wp in map_data.waypoints:
        print(f"      - {wp.name}")
    print(f"   Spawns: {len(map_data.spawns)}")
    print(f"   NPCs: {len(map_data.npc_spawns)}")
    for npc in map_data.npc_spawns:
        print(f"      - {npc.npc_name} at ({npc.x}, {npc.y}, {npc.z})")

    return 0


def cmd_convert(args):
    """Convert between OTBM and JSON formats."""
    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        return 1

    fmt = args.format.lower()

    try:
        map_data = _load_map(filepath)
    except Exception as e:
        print(f"❌ Failed to read file: {e}", file=sys.stderr)
        return 1

    output = args.output

    if fmt == "json":
        if not output:
            output = filepath.rsplit(".", 1)[0] + ".json"
        _save_json(map_data, output)
        print(f"✅ Converted to JSON: {output}")
        return 0

    elif fmt == "otbm":
        if not output:
            output = filepath.rsplit(".", 1)[0] + ".otbm"
        _save_otbm(map_data, output)
        print(f"✅ Converted to OTBM: {output}")
        return 0

    else:
        print(f"❌ Unknown format: {fmt}. Use 'json' or 'otbm'.", file=sys.stderr)
        return 1


def cmd_diff(args):
    """Compare two map files and show differences."""
    from ai_core.map_diff import MapDiff

    path_a = args.map1
    path_b = args.map2

    for p in (path_a, path_b):
        if not os.path.exists(p):
            print(f"❌ File not found: {p}", file=sys.stderr)
            return 1

    try:
        result = MapDiff.compare_files(path_a, path_b)
    except Exception as e:
        print(f"❌ Failed to compare maps: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_json(), indent=2))
    else:
        if args.detailed:
            print(result.detailed())
        else:
            print(result.summary())

    return 0


def cmd_analyze(args):
    """Run biome analysis on a map file."""
    from ai_core.biome_analyzer import BiomeAnalyzer

    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}", file=sys.stderr)
        return 1

    try:
        report = BiomeAnalyzer.from_file(filepath, store_heatmap=True)
    except Exception as e:
        print(f"❌ Failed to analyze map: {e}", file=sys.stderr)
        return 1

    print(report.summary())
    print()
    print(report.heatmap())
    return 0


def cmd_batch(args):
    """Run batch generation from a config file."""
    from ai_core.batch_generator import load_batch_config, generate_batch

    config_path = args.config
    if not os.path.exists(config_path):
        print(f"❌ Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        batch_cfg = load_batch_config(config_path)
    except (ValueError, ImportError) as e:
        print(f"❌ Failed to load config: {e}", file=sys.stderr)
        return 1

    if not batch_cfg.maps:
        print("❌ No maps defined in config", file=sys.stderr)
        return 1

    print(f"📦 Batch generation: {len(batch_cfg.maps)} map(s) -> {batch_cfg.output_dir}")

    def progress(i, total, name, status):
        icon = "✅" if status == "done" else "⚙️"
        print(f"  {icon} [{i + 1}/{total}] {name}: {status}")

    start = time.time()
    try:
        files = generate_batch(batch_cfg, progress_callback=progress)
    except Exception as e:
        print(f"❌ Batch generation failed: {e}", file=sys.stderr)
        return 1

    elapsed = time.time() - start
    print(f"\n✅ Batch complete: {len(files)} maps in {elapsed:.2f}s")
    for f in files:
        size = os.path.getsize(f) if os.path.exists(f) else 0
        print(f"   {f} ({size:,} bytes)")
    return 0


def cmd_quest(args):
    """Add a quest area to an existing map."""
    from ai_core.generators.quest import (
        QuestGenerator, QuestTemplate,
        DragonSlayerQuest, TombRaiderQuest, ElvenRuinsQuest,
        IceCaveQuest, DemonCryptQuest, PirateCoveQuest,
        SpiderNestQuest, OrcFortressQuest, VampireManorQuest,
        DwarvenMinesQuest, AncientTempleQuest, BanditHideoutQuest,
    )

    map_path = args.map_file
    if not os.path.exists(map_path):
        print(f"❌ Map file not found: {map_path}", file=sys.stderr)
        return 1

    # Parse position
    pos_parts = args.position.split(",")
    if len(pos_parts) != 3:
        print(f"❌ Invalid position format: {args.position} (expected x,y,z)", file=sys.stderr)
        return 1
    from ai_core.models import Position
    position = Position(
        x=int(pos_parts[0].strip()),
        y=int(pos_parts[1].strip()),
        z=int(pos_parts[2].strip()),
    )

    # Load map
    try:
        map_data = _load_map(map_path)
    except Exception as e:
        print(f"❌ Failed to load map: {e}", file=sys.stderr)
        return 1

    # Select quest template
    quest_name = args.quest_name.lower() if args.quest_name else ""
    template_map = {
        "dragon": DragonSlayerQuest(),
        "tomb": TombRaiderQuest(),
        "elven": ElvenRuinsQuest(),
        "ice": IceCaveQuest(),
        "demon": DemonCryptQuest(),
        "pirate": PirateCoveQuest(),
        "spider": SpiderNestQuest(),
        "orc": OrcFortressQuest(),
        "vampire": VampireManorQuest(),
        "dwarven": DwarvenMinesQuest(),
        "temple": AncientTempleQuest(),
        "bandit": BanditHideoutQuest(),
    }

    # Find matching template
    template = None
    for key, tmpl in template_map.items():
        if key in quest_name:
            template = tmpl
            break

    if template is None:
        # Create a custom template from the quest name
        template = QuestTemplate(name=args.quest_name or "Custom Quest", description="Custom quest area")

    print(f"⚔️  Adding quest: {template.name}")
    print(f"   Position: ({position.x}, {position.y}, {position.z})")
    print(f"   Difficulty: {template.difficulty.value}")

    gen = QuestGenerator(seed=args.seed if args.seed is not None else 42)
    gen.generate_quest(map_data, template, position)

    # Save result
    output = args.output or map_path
    _save_otbm(map_data, output)

    elapsed_str = ""
    print(f"✅ Quest '{template.name}' added to map")
    print(f"   Output: {output}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# Argument parser
# ═══════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="otbforge",
        description="OTBForge — Generate, validate, and convert Tibia OTBM maps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  otbforge generate terrain --size 256 --seed 42 --output island.otbm
  otbforge generate dungeon --rooms 10 --floors 3 --output dungeon.otbm
  otbforge generate ai --prompt "isla tropical con pueblo pirata" --output pirate.otbm
  otbforge validate map.otbm
  otbforge info map.otbm
  otbforge convert map.otbm --format json
  otbforge convert map.json --format otbm --output map.otbm
        """,
    )
    parser.add_argument("--version", action="version", version="OTBForge 0.2.0")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # ─── generate ───────────────────────────────────────────────────────
    gen_parser = subparsers.add_parser("generate", aliases=["gen"], help="Generate a map")

    # generate terrain
    terrain_parser = gen_parser.add_subparsers(dest="subcommand", help="Generator type")
    t_parser = terrain_parser.add_parser("terrain", aliases=["t"], help="Generate terrain")
    t_parser.add_argument("--size", "-s", type=int, default=256, help="Map size (default: 256)")
    t_parser.add_argument("--seed", type=int, default=None, help="Random seed")
    t_parser.add_argument("--water-level", type=float, default=None, help="Water level (0-1)")
    t_parser.add_argument("--biome", choices=["plains", "forest", "mountain", "desert", "snow"], default=None)
    t_parser.add_argument("--output", "-o", default="terrain.otbm", help="Output file")

    # generate dungeon
    d_parser = terrain_parser.add_parser("dungeon", aliases=["d"], help="Generate dungeon")
    d_parser.add_argument("--size", "-s", type=int, default=50, help="Map size (default: 50)")
    d_parser.add_argument("--rooms", "-r", type=int, default=8, help="Number of rooms (default: 8)")
    d_parser.add_argument("--floors", "-f", type=int, default=1, help="Number of floors (default: 1)")
    d_parser.add_argument("--seed", type=int, default=None, help="Random seed")
    d_parser.add_argument("--output", "-o", default="dungeon.otbm", help="Output file")

    # generate ai
    ai_parser = terrain_parser.add_parser("ai", aliases=["a"], help="Generate via AI/LLM")
    ai_parser.add_argument("prompt", nargs="?", help="Text description of the map")
    ai_parser.add_argument("--output", "-o", default="ai_map.otbm", help="Output file")
    ai_parser.add_argument("--seed", type=int, default=None, help="Random seed")
    ai_parser.add_argument("--api-key", default=None, help="LLM API key")
    ai_parser.add_argument("--api-url", default=None, help="LLM API base URL")
    ai_parser.add_argument("--model", default="glm-5-turbo", help="LLM model name")

    # ─── validate ──────────────────────────────────────────────────────
    val_parser = subparsers.add_parser("validate", aliases=["val", "v"], help="Validate map file")
    val_parser.add_argument("file", help="OTBM or JSON file to validate")

    # ─── info ──────────────────────────────────────────────────────────
    info_parser = subparsers.add_parser("info", aliases=["i"], help="Show map information")
    info_parser.add_argument("file", help="OTBM or JSON file")

    # ─── convert ───────────────────────────────────────────────────────
    conv_parser = subparsers.add_parser("convert", aliases=["conv", "c"], help="Convert map format")
    conv_parser.add_argument("file", help="OTBM or JSON file to convert")
    conv_parser.add_argument("--format", "-f", required=True, choices=["json", "otbm"],
                             help="Target format")
    conv_parser.add_argument("--output", "-o", default=None, help="Output file")

    # ─── diff ──────────────────────────────────────────────────────────
    diff_parser = subparsers.add_parser("diff", help="Compare two map files")
    diff_parser.add_argument("map1", help="First map file (OTBM or JSON)")
    diff_parser.add_argument("map2", help="Second map file (OTBM or JSON)")
    diff_parser.add_argument("--json", action="store_true", help="Output as JSON")
    diff_parser.add_argument("--detailed", "-d", action="store_true", help="Show detailed diff")

    # ─── analyze ───────────────────────────────────────────────────────
    analyze_parser = subparsers.add_parser("analyze", aliases=["analysis"], help="Biome analysis")
    analyze_parser.add_argument("file", help="OTBM or JSON file to analyze")

    # ─── batch ─────────────────────────────────────────────────────────
    batch_parser = subparsers.add_parser("batch", help="Batch generation from config file")
    batch_parser.add_argument("config", help="JSON or YAML batch config file")

    # ─── quest ─────────────────────────────────────────────────────────
    quest_parser = subparsers.add_parser("quest", help="Add a quest area to a map")
    quest_parser.add_argument("map_file", help="OTBM or JSON map file")
    quest_parser.add_argument("--name", "-n", dest="quest_name", default="dragon",
                              help="Quest template name (dragon, tomb, elven, ice, demon, pirate, spider, orc, vampire, dwarven, temple, bandit)")
    quest_parser.add_argument("--position", "-p", required=True,
                              help="Quest position as x,y,z (e.g. 100,100,7)")
    quest_parser.add_argument("--seed", type=int, default=None, help="Random seed")
    quest_parser.add_argument("--output", "-o", default=None, help="Output file (default: overwrite input)")

    return parser


def main(argv: list = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in ("generate", "gen"):
        if args.subcommand in ("terrain", "t"):
            return cmd_generate_terrain(args)
        elif args.subcommand in ("dungeon", "d"):
            return cmd_generate_dungeon(args)
        elif args.subcommand in ("ai", "a"):
            if not args.prompt:
                parser.print_help()
                return 1
            return cmd_generate_ai(args)
        else:
            parser.print_help()
            return 1

    elif args.command in ("validate", "val", "v"):
        return cmd_validate(args)

    elif args.command in ("info", "i"):
        return cmd_info(args)

    elif args.command in ("convert", "conv", "c"):
        return cmd_convert(args)

    elif args.command == "diff":
        return cmd_diff(args)

    elif args.command in ("analyze", "analysis"):
        return cmd_analyze(args)

    elif args.command == "batch":
        return cmd_batch(args)

    elif args.command == "quest":
        return cmd_quest(args)

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
