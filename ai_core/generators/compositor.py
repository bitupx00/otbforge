"""Map compositor: full pipeline for generating complete maps.

Orchestrates the full generation pipeline:
  terrain → roads → towns → spawns → houses → vegetation → water features

Provides a single-call FullMapGenerator and per-stage customization hooks.
Each stage can be enabled/disabled and configured independently.

Features:
  - FullMapGenerator: one-call complete map generation
  - Stage hooks: before/after callbacks for each stage
  - Per-stage configuration
  - Deterministic seed-based generation
  - OTBM round-trip support
"""

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ai_core.otbm_types import (
    MapData,
    TileData,
)
from ai_core.generators.terrain import TerrainGenerator
from ai_core.generators.road_generator import RoadGenerator, RoadTiles
from ai_core.generators.water_features import WaterFeatureGenerator
from ai_core.generators.vegetation import VegetationEnhancer
from ai_core.generators.town import TownGenerator
from ai_core.generators.spawn_manager import SpawnManager


# ---------------------------------------------------------------------------
# Stage hook type
# ---------------------------------------------------------------------------

StageHook = Callable[[str, Optional[MapData]], Optional[MapData]]


# ---------------------------------------------------------------------------
# Compositor config
# ---------------------------------------------------------------------------

@dataclass
class CompositorConfig:
    """Configuration for the full map generation pipeline."""
    width: int = 128
    height: int = 128
    seed: int = 42

    # Terrain
    water_level: float = 0.38
    biome_scale: float = 0.02
    rivers: bool = True
    num_rivers: int = 2

    # Roads
    road_network: bool = True
    num_road_waypoints: int = 0  # 0 = auto-generate from towns
    road_width: int = 1

    # Towns
    num_towns: int = 2
    town_size: int = 20
    town_style: str = "medieval"
    town_layout: str = "grid"
    town_seed_offset: int = 0

    # Spawns
    monster_density: float = 0.5
    spawn_difficulty: int = 3

    # Vegetation
    vegetation: bool = True
    tree_density: float = 0.10
    num_tree_clusters: int = 6
    flower_density: float = 0.05
    num_hedge_rows: int = 1

    # Water features
    water_features: bool = True
    num_lakes: int = 2
    num_wells: int = 1
    num_oases: int = 1
    num_fountains: int = 1

    # Dungeons (skip in compositor, kept for API completeness)
    dungeon_count: int = 0


# ---------------------------------------------------------------------------
# FullMapGenerator
# ---------------------------------------------------------------------------

@dataclass
class FullMapGenerator:
    """Full map generation pipeline with stage hooks.

    Parameters
    ----------
    config : CompositorConfig
        Full pipeline configuration.
    stage_hooks : dict
        Optional before/after hooks per stage.
        Keys: "before_terrain", "after_terrain", etc.
        Values: callable(stage_name, map_data) -> map_data or None
    """
    config: CompositorConfig = field(default_factory=CompositorConfig)
    stage_hooks: Dict[str, StageHook] = field(default_factory=dict)

    def generate(self) -> MapData:
        """Run the full generation pipeline and return complete MapData."""
        cfg = self.config

        # ---- Stage 1: Terrain ----
        map_data = self._run_hook("before_terrain", None)
        terrain_gen = TerrainGenerator(
            width=cfg.width,
            height=cfg.height,
            seed=cfg.seed,
            water_level=cfg.water_level,
            biome_scale=cfg.biome_scale,
            rivers=cfg.rivers,
            num_rivers=cfg.num_rivers,
        )
        map_data = terrain_gen.generate()
        map_data = self._run_hook("after_terrain", map_data) or map_data

        # ---- Stage 2: Towns ----
        map_data = self._run_hook("before_towns", map_data) or map_data
        if cfg.num_towns > 0:
            town_gen = TownGenerator(
                center_x=cfg.width // 2,
                center_y=cfg.height // 2,
                size=cfg.town_size,
                town_id=1,
                town_name=f"Town_{cfg.seed}",
                style=cfg.town_style,
                layout=cfg.town_layout,
                seed=cfg.seed + cfg.town_seed_offset,
                map_width=cfg.width,
                map_height=cfg.height,
            )
            map_data = town_gen.generate(base_map=map_data)

            # Place additional towns at different locations
            for i in range(1, cfg.num_towns):
                offset_x = random.Random(cfg.seed + i * 1000).randint(-cfg.width // 4, cfg.width // 4)
                offset_y = random.Random(cfg.seed + i * 2000).randint(-cfg.height // 4, cfg.height // 4)
                town_gen = TownGenerator(
                    center_x=max(cfg.town_size, min(cfg.width - cfg.town_size, cfg.width // 2 + offset_x)),
                    center_y=max(cfg.town_size, min(cfg.height - cfg.town_size, cfg.height // 2 + offset_y)),
                    size=cfg.town_size,
                    town_id=i + 1,
                    town_name=f"Town_{cfg.seed}_{i + 1}",
                    style=cfg.town_style,
                    layout=cfg.town_layout,
                    seed=cfg.seed + i * 1000 + cfg.town_seed_offset,
                    map_width=cfg.width,
                    map_height=cfg.height,
                )
                map_data = town_gen.generate(base_map=map_data)

        map_data = self._run_hook("after_towns", map_data) or map_data

        # ---- Stage 3: Roads ----
        map_data = self._run_hook("before_roads", map_data) or map_data
        if cfg.road_network and cfg.num_towns > 0:
            road_gen = RoadGenerator(
                map_data=map_data,
                seed=cfg.seed,
                width=cfg.road_width,
            )
            waypoints = []
            for town in map_data.towns:
                waypoints.append((town.temple.x, town.temple.y))

            if len(waypoints) >= 2:
                paths = road_gen.generate_network(waypoints)
                for path in paths:
                    if path:
                        map_data = road_gen.apply_path(path)
                        road_gen = RoadGenerator(
                            map_data=map_data,
                            seed=cfg.seed,
                            width=cfg.road_width,
                        )

        map_data = self._run_hook("after_roads", map_data) or map_data

        # ---- Stage 4: Water features ----
        map_data = self._run_hook("before_water", map_data) or map_data
        if cfg.water_features:
            water_gen = WaterFeatureGenerator(
                map_data=map_data,
                seed=cfg.seed,
                num_lakes=cfg.num_lakes,
                num_wells=cfg.num_wells,
                num_oases=cfg.num_oases,
                num_fountains=cfg.num_fountains,
            )
            map_data = water_gen.generate()

        map_data = self._run_hook("after_water", map_data) or map_data

        # ---- Stage 5: Vegetation ----
        map_data = self._run_hook("before_vegetation", map_data) or map_data
        if cfg.vegetation:
            veg_gen = VegetationEnhancer(
                map_data=map_data,
                seed=cfg.seed,
                tree_density=cfg.tree_density,
                flower_density=cfg.flower_density,
                num_tree_clusters=cfg.num_tree_clusters,
                num_hedge_rows=cfg.num_hedge_rows,
            )
            map_data = veg_gen.enhance()

        map_data = self._run_hook("after_vegetation", map_data) or map_data

        # ---- Stage 6: Spawns ----
        map_data = self._run_hook("before_spawns", map_data) or map_data
        spawn_mgr = SpawnManager(
            map_data=map_data,
            seed=cfg.seed,
            difficulty=cfg.spawn_difficulty,
            monster_density=cfg.monster_density,
        )
        map_data = spawn_mgr.generate()
        map_data = self._run_hook("after_spawns", map_data) or map_data

        return map_data

    def generate_terrain_only(self) -> MapData:
        """Generate only terrain (stage 1)."""
        cfg = self.config
        terrain_gen = TerrainGenerator(
            width=cfg.width,
            height=cfg.height,
            seed=cfg.seed,
            water_level=cfg.water_level,
            biome_scale=cfg.biome_scale,
            rivers=cfg.rivers,
            num_rivers=cfg.num_rivers,
        )
        return terrain_gen.generate()

    def generate_with_towns(self) -> MapData:
        """Generate terrain + towns (stages 1-2)."""
        cfg = self.config
        map_data = self.generate_terrain_only()

        if cfg.num_towns > 0:
            town_gen = TownGenerator(
                center_x=cfg.width // 2,
                center_y=cfg.height // 2,
                size=cfg.town_size,
                town_id=1,
                town_name=f"Town_{cfg.seed}",
                style=cfg.town_style,
                layout=cfg.town_layout,
                seed=cfg.seed,
                map_width=cfg.width,
                map_height=cfg.height,
            )
            map_data = town_gen.generate(base_map=map_data)

        return map_data

    def _run_hook(self, name: str, map_data: Optional[MapData]) -> Optional[MapData]:
        """Run a stage hook if registered."""
        hook = self.stage_hooks.get(name)
        if hook:
            result = hook(name, map_data)
            return result
        return None
