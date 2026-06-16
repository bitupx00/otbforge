"""Map generators: terrain (Perlin), dungeon (BSP), city (grid), spawns, town, house placer,
road (A* with bridges), water features (lakes, wells, oases), vegetation (clusters),
and compositor (full pipeline)."""

from ai_core.generators.city import CityGenerator
from ai_core.generators.compositor import CompositorConfig, FullMapGenerator
from ai_core.generators.dungeon import DungeonGenerator
from ai_core.generators.road_generator import RoadGenerator, RoadTiles
from ai_core.generators.spawns import SpawnGenerator
from ai_core.generators.spawn_manager import SpawnManager
from ai_core.generators.terrain import TerrainGenerator
from ai_core.generators.town import TownGenerator
from ai_core.generators.house_placer import HousePlacer
from ai_core.generators.vegetation import VegetationEnhancer
from ai_core.generators.water_features import WaterFeatureGenerator

__all__ = [
    "TerrainGenerator",
    "DungeonGenerator",
    "CityGenerator",
    "SpawnGenerator",
    "TownGenerator",
    "SpawnManager",
    "HousePlacer",
    "RoadGenerator",
    "RoadTiles",
    "WaterFeatureGenerator",
    "VegetationEnhancer",
    "CompositorConfig",
    "FullMapGenerator",
]
