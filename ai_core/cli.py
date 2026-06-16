#!/usr/bin/env python3
"""Tibia AI Mapper CLI — Generate Tibia OTBM maps from text descriptions.

Usage:
    python -m ai_core.cli "una isla 256x256 con bosque y ciudad amurallada" -o mapa.otbm
    python -m ai_core.cli "dungeon de 3 pisos con 10 habitaciones" -o dungeon.otbm --seed 42
    python -m ai_core.cli "ciudad con parque y spawns" -o city.otbm --api-key KEY --api-url URL

Modes:
    prompt    — Generate from text description (default)
    terrain   — Generate terrain only
    dungeon   — Generate dungeon only
    city      — Generate city only
    info      — Read and display OTBM file info
"""

import argparse
import json
import sys
import time
import os

# Add parent dir to path for -m execution
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_core.llm_bridge import LLMMapGenerator
from ai_core.otbm_reader import OTBMReader
from ai_core.otbm_types import MapData


def cmd_generate(args):
    """Generate a map from prompt."""
    gen = LLMMapGenerator(
        api_key=args.api_key,
        base_url=args.api_url,
        model=args.model,
    )

    prompt = args.prompt
    output = args.output
    seed = args.seed

    print(f"🌍 Generating map from: '{prompt}'")
    start = time.time()

    result = gen.generate(prompt, output_file=output, seed=seed)

    elapsed = time.time() - start
    tile_count = len(result.tiles)
    map_size = os.path.getsize(output) if output and os.path.exists(output) else 0

    print(f"✅ Map generated in {elapsed:.2f}s")
    print(f"   Tiles: {tile_count:,}")
    print(f"   Towns: {len(result.towns)}")
    print(f"   Waypoints: {len(result.waypoints)}")
    print(f"   Spawns: {len(result.spawns)}")
    print(f"   NPCs: {len(result.npc_spawns)}")
    if output and map_size > 0:
        print(f"   File: {output} ({map_size:,} bytes)")


def cmd_info(args):
    """Display info about an OTBM file."""
    filepath = args.file
    if not os.path.exists(filepath):
        print(f"❌ File not found: {filepath}")
        return 1

    reader = OTBMReader(data=open(filepath, "rb").read())
    map_data = reader.read()

    print(f"🗺️  Map: {map_data.description}")
    print(f"   Size: {map_data.width}x{map_data.height}")
    print(f"   OTBM Version: {map_data.otbm_version}")
    print(f"   Tiles: {len(map_data.tiles):,}")

    # Count by z-level
    z_levels = {}
    for tile in map_data.tiles:
        z = tile.z
        z_levels[z] = z_levels.get(z, 0) + 1
    print(f"   Z-levels: {dict(sorted(z_levels.items()))}")

    # Ground type distribution
    ground_types = {}
    for tile in map_data.tiles:
        g = tile.ground_id
        ground_types[g] = ground_types.get(g, 0) + 1
    top_grounds = sorted(ground_types.items(), key=lambda x: -x[1])[:10]
    print(f"   Top ground types: {[(f'0x{g:04X}', c) for g, c in top_grounds]}")

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


def main():
    parser = argparse.ArgumentParser(
        description="Tibia AI Mapper — Generate Tibia OTBM maps from text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "una isla con bosque" -o island.otbm
  %(prog)s "dungeon 3 pisos 10 rooms" -o dungeon.otbm --seed 42
  %(prog)s "ciudad amurallada con parque" -o city.otbm
  %(prog)s info mapa.otbm
        """,
    )
    parser.add_argument("--version", action="version", version="Tibia AI Mapper 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Generate command (default)
    gen_parser = subparsers.add_parser("generate", aliases=["gen", "g"], help="Generate map from prompt")
    gen_parser.add_argument("prompt", nargs="?", help="Text description of the map")
    gen_parser.add_argument("-o", "--output", default="output.otbm", help="Output OTBM file (default: output.otbm)")
    gen_parser.add_argument("--seed", type=int, default=None, help="Random seed")
    gen_parser.add_argument("--api-key", default=None, help="LLM API key (optional)")
    gen_parser.add_argument("--api-url", default=None, help="LLM API base URL (optional)")
    gen_parser.add_argument("--model", default="glm-5-turbo", help="LLM model name (default: glm-5-turbo)")

    # Info command
    info_parser = subparsers.add_parser("info", aliases=["i"], help="Display OTBM file info")
    info_parser.add_argument("file", help="OTBM file path")

    args = parser.parse_args()

    if args.command in ("info", "i"):
        return cmd_info(args)
    else:
        # Default to generate
        if not args.prompt and not hasattr(args, 'prompt'):
            parser.print_help()
            return 1
        prompt = getattr(args, 'prompt', None)
        if not prompt:
            # Try positional from sys.argv
            if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
                prompt = sys.argv[1]
                args.output = args.output or "output.otbm"
            else:
                parser.print_help()
                return 1
        return cmd_generate(args)


if __name__ == "__main__":
    sys.exit(main())
