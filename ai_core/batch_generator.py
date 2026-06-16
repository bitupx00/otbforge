"""Batch Generator — Generate multiple maps from a YAML/JSON config.

Supports batch generation of multiple maps with per-map configuration
including size, seed, biome, and generator selection.

Config formats supported:
  - JSON (.json)
  - YAML (.yaml, .yml)

Usage::

    from ai_core.batch_generator import BatchConfig, generate_batch, generate_from_prompt_list

    config = BatchConfig(output_dir="./maps", maps=[
        MapGenConfig(name="forest", size=128, seed=42, generators=["terrain"]),
        MapGenConfig(name="dungeon", size=64, seed=100, generators=["dungeon"]),
    ])
    files = generate_batch(config)
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai_core.models import MapData, Position


# ---------------------------------------------------------------------------
# Map generation config (per-map)
# ---------------------------------------------------------------------------

@dataclass
class MapGenConfig:
    """Configuration for a single map in a batch."""
    name: str = "map"
    size: int = 128
    seed: int = 42
    biome: str = ""  # "", "plains", "forest", "mountain", "desert", "snow"
    generators: List[str] = field(default_factory=lambda: ["terrain"])
    # Extra parameters forwarded to generators
    water_level: Optional[float] = None
    rooms: int = 8
    floors: int = 1
    output_format: str = "otbm"  # "otbm" or "json"
    # LLM prompt (used when "ai" generator is selected)
    prompt: str = ""


# ---------------------------------------------------------------------------
# Batch config
# ---------------------------------------------------------------------------

@dataclass
class BatchConfig:
    """Configuration for a batch generation run."""
    output_dir: str = "./output"
    maps: List[MapGenConfig] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, str, str], None]


def _generate_single_map(cfg: MapGenConfig, output_path: str) -> str:
    """Generate a single map from a MapGenConfig. Returns the output file path."""
    if "ai" in cfg.generators:
        return _generate_ai_map(cfg, output_path)
    elif "dungeon" in cfg.generators:
        return _generate_dungeon_map(cfg, output_path)
    else:
        return _generate_terrain_map(cfg, output_path)


def _generate_terrain_map(cfg: MapGenConfig, output_path: str) -> str:
    """Generate a terrain-based map."""
    from ai_core.generators.compositor import CompositorConfig, FullMapGenerator

    compositor_cfg = CompositorConfig(
        width=cfg.size,
        height=cfg.size,
        seed=cfg.seed,
    )
    if cfg.water_level is not None:
        compositor_cfg.water_level = cfg.water_level

    if cfg.biome:
        biome_scale_map = {
            "plains": 0.02, "forest": 0.03, "mountain": 0.04,
            "desert": 0.01, "snow": 0.02,
        }
        compositor_cfg.biome_scale = biome_scale_map.get(cfg.biome, 0.02)
        if cfg.biome == "forest":
            compositor_cfg.water_level = compositor_cfg.water_level if cfg.water_level is not None else 0.3
        elif cfg.biome == "desert":
            compositor_cfg.water_level = compositor_cfg.water_level if cfg.water_level is not None else 0.0

    gen = FullMapGenerator(config=compositor_cfg)
    map_data = gen.generate()

    return _save_map(map_data, output_path, cfg.output_format)


def _generate_dungeon_map(cfg: MapGenConfig, output_path: str) -> str:
    """Generate a dungeon map."""
    from ai_core.generators.dungeon import DungeonGenerator

    gen = DungeonGenerator(
        width=cfg.size,
        height=cfg.size,
        rooms_count=cfg.rooms,
        seed=cfg.seed,
    )
    map_data = gen.generate()
    return _save_map(map_data, output_path, cfg.output_format)


def _generate_ai_map(cfg: MapGenConfig, output_path: str) -> str:
    """Generate a map via AI/LLM (mock for testing)."""
    from ai_core.llm_bridge import LLMMapGenerator

    prompt = cfg.prompt or f"Generate a {cfg.biome or 'fantasy'} map"
    gen = LLMMapGenerator()
    result = gen.generate(prompt, output_file=output_path, seed=cfg.seed)
    return output_path


def _save_map(map_data: MapData, output_path: str, fmt: str) -> str:
    """Save a MapData to file."""
    if fmt == "json":
        from ai_core.cli import _save_json
        _save_json(map_data, output_path)
    else:
        from ai_core.otbm_writer import OTBMWriter
        writer = OTBMWriter(map_data)
        writer.save(output_path)
    return output_path


def generate_batch(
    config: BatchConfig,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[str]:
    """Generate all maps in a BatchConfig.

    Parameters
    ----------
    config : BatchConfig
        Batch configuration with output dir and map list.
    progress_callback : callable, optional
        Called as progress_callback(current_index, total, map_name, status).

    Returns
    -------
    list[str]
        List of generated file paths.
    """
    os.makedirs(config.output_dir, exist_ok=True)
    generated_files = []
    total = len(config.maps)

    for i, map_cfg in enumerate(config.maps):
        name = map_cfg.name
        if progress_callback:
            progress_callback(i, total, name, "generating")

        ext = map_cfg.output_format
        output_path = os.path.join(config.output_dir, f"{name}.{ext}")

        try:
            result_path = _generate_single_map(map_cfg, output_path)
            generated_files.append(result_path)
            if progress_callback:
                progress_callback(i, total, name, "done")
        except Exception as e:
            if progress_callback:
                progress_callback(i, total, name, f"error: {e}")
            raise

    return generated_files


def generate_from_prompt_list(
    prompts: List[str],
    output_dir: str = "./output",
    size: int = 128,
    seed: int = 42,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[str]:
    """Generate multiple maps from a list of text prompts.

    Parameters
    ----------
    prompts : list[str]
        Text prompts for each map.
    output_dir : str
        Directory for generated files.
    size : int
        Map size for all generated maps.
    seed : int
        Base seed (incremented per map).
    progress_callback : callable, optional
        Called as progress_callback(current_index, total, map_name, status).

    Returns
    -------
    list[str]
        List of generated file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    total = len(prompts)

    for i, prompt in enumerate(prompts):
        name = f"prompt_{i}"
        if progress_callback:
            progress_callback(i, total, name, "generating")

        from ai_core.llm_bridge import LLMMapGenerator
        output_path = os.path.join(output_dir, f"{name}.otbm")
        gen = LLMMapGenerator()
        gen.generate(prompt, output_file=output_path, seed=seed + i)
        generated_files.append(output_path)

        if progress_callback:
            progress_callback(i, total, name, "done")

    return generated_files


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_batch_config(path: str) -> BatchConfig:
    """Load a BatchConfig from a JSON or YAML file.

    Parameters
    ----------
    path : str
        Path to the config file (.json, .yaml, .yml).

    Returns
    -------
    BatchConfig
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        raw = f.read()

    if path.endswith((".yaml", ".yml")):
        data = _parse_yaml(raw)
    elif path.endswith(".json"):
        data = json.loads(raw)
    else:
        # Try JSON first, then YAML
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = _parse_yaml(raw)

    return _parse_batch_config(data)


def _parse_yaml(raw: str) -> dict:
    """Parse YAML string, raising if pyyaml is not installed."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required for YAML config files. "
            "Install it with: pip install pyyaml"
        )
    return yaml.safe_load(raw)


def _parse_batch_config(data: dict) -> BatchConfig:
    """Parse a raw dict into a BatchConfig."""
    output_dir = data.get("output_dir", "./output")

    maps = []
    for m in data.get("maps", []):
        map_cfg = MapGenConfig(
            name=m.get("name", "map"),
            size=m.get("size", 128),
            seed=m.get("seed", 42),
            biome=m.get("biome", ""),
            generators=m.get("generators", ["terrain"]),
            water_level=m.get("water_level"),
            rooms=m.get("rooms", 8),
            floors=m.get("floors", 1),
            output_format=m.get("output_format", "otbm"),
            prompt=m.get("prompt", ""),
        )
        maps.append(map_cfg)

    return BatchConfig(output_dir=output_dir, maps=maps)
