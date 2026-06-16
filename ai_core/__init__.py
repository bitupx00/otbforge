"""Tibia AI Mapper — AI-powered Tibia map generation.

Core package containing OTBM binary format support:
- models.py: Data models, constants, enums (Position, TileData, ItemData, …)
- otbm_writer.py: Full OTBM v2/v3 binary writer
- otbm_reader.py: Full OTBM v2/v3 binary reader
"""

from .models import (
    Attr,
    ESCAPE,
    ESCAPE_THRESHOLD,
    HouseData,
    ItemData,
    MapData,
    NPCSpawnData,
    NODE_END,
    NODE_START,
    NodeType,
    OtbVersion,
    OTB_V2_7,
    OTB_V3_12,
    OTBM_MAGIC,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TileFlags,
    Tiles,
    TownData,
    WaypointData,
)
from .otbm_writer import OTBMWriter
from .otbm_reader import OTBMReader

# Backward-compat re-exports from old otbm_types module
from .models import (  # noqa: F401 — re-export for compat
    TileData as _TileDataCompat,
    ItemData as _ItemDataCompat,
)

__all__ = [
    # Constants
    "ESCAPE", "ESCAPE_THRESHOLD", "NODE_END", "NODE_START",
    "OTBM_MAGIC",
    "NodeType", "Attr", "TileFlag", "TileFlags", "Tiles",
    "OtbVersion", "OTB_V2_7", "OTB_V3_12",
    # Models
    "Position", "ItemData", "TileData", "TownData", "WaypointData",
    "SpawnData", "NPCSpawnData", "HouseData", "MapData",
    # IO
    "OTBMWriter", "OTBMReader",
]

__version__ = "0.2.0"
