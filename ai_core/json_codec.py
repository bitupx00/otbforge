"""
JSON Export/Import Codec — Convert OTBM MapData to/from editable JSON.

Provides:
- ``MapJsonCodec.encode(map_data)``  → dict   (MapData → JSON-compatible dict)
- ``MapJsonCodec.decode(data)``       → MapData (JSON dict → MapData)
- ``MapJsonCodec.save(map_data, path)``        — write .json
- ``MapJsonCodec.load(path)``                  — read .json
- ``MapJsonCodec.export_otbm(map_data, path)`` — .otbm → .json
- ``MapJsonCodec.import_otbm(json_path, otbm_path)`` — .json → .otbm

The JSON format preserves ALL data: tiles, towns, waypoints, spawns,
NPC spawns, and houses.

Usage::

    from ai_core.json_codec import MapJsonCodec

    # Save OTBM as JSON
    MapJsonCodec.export_otbm(map_data, "map.json")

    # Load JSON as MapData
    md = MapJsonCodec.load("map.json")

    # Compact mode for smaller files
    dct = MapJsonCodec.encode(md, compact=True)
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ai_core.models import (
    HouseData,
    ItemData,
    MapData,
    NPCSpawnData,
    Position,
    SpawnData,
    TileData,
    TileFlag,
    TownData,
    WaypointData,
)
from ai_core.otbm_reader import OTBMReader
from ai_core.otbm_writer import OTBMWriter

_CODEC_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pos_to_dict(pos: Position) -> Dict[str, int]:
    return {"x": pos.x, "y": pos.y, "z": pos.z}


def _pos_from_dict(d: Dict[str, Any]) -> Position:
    if isinstance(d, (list, tuple)):
        return Position(x=d[0], y=d[1], z=d[2] if len(d) > 2 else 7)
    return Position(x=d["x"], y=d["y"], z=d.get("z", 7))


def _item_to_dict(item: ItemData, compact: bool = False) -> Dict[str, Any]:
    if compact:
        # Only id + count if non-default
        base = {"id": item.id}
        extras: Dict[str, Any] = {}
        if item.count:
            extras["count"] = item.count
        if item.action_id:
            extras["action_id"] = item.action_id
        if item.unique_id:
            extras["unique_id"] = item.unique_id
        if item.text:
            extras["text"] = item.text
        if item.description:
            extras["desc"] = item.description
        if item.charges:
            extras["charges"] = item.charges
        if item.house_door_id:
            extras["door_id"] = item.house_door_id
        if item.depot_id:
            extras["depot_id"] = item.depot_id
        if item.teleport_dest:
            extras["tele_dest"] = _pos_to_dict(item.teleport_dest)
        if item.duration:
            extras["duration"] = item.duration
        if item.decay_state:
            extras["decay"] = item.decay_state
        if item.written_date:
            extras["written_date"] = item.written_date
        if item.written_by:
            extras["written_by"] = item.written_by
        if item.rune_charges:
            extras["rune_charges"] = item.rune_charges
        if item.children:
            extras["children"] = [_item_to_dict(c, compact=True) for c in item.children]
        base.update(extras)
        return base

    return {
        "item_id": item.id,
        "count": item.count,
        "action_id": item.action_id,
        "unique_id": item.unique_id,
        "text": item.text,
        "description": item.description,
        "charges": item.charges,
        "house_door_id": item.house_door_id,
        "depot_id": item.depot_id,
        "teleport_dest": _pos_to_dict(item.teleport_dest) if item.teleport_dest else None,
        "duration": item.duration,
        "decay_state": item.decay_state,
        "written_date": item.written_date,
        "written_by": item.written_by,
        "rune_charges": item.rune_charges,
        "sleeper_guid": item.sleeper_guid,
        "sleep_start": item.sleep_start,
        "children": [_item_to_dict(c, compact=False) for c in item.children],
    }


def _item_from_dict(d: Dict[str, Any]) -> ItemData:
    # Support both "item_id" and "id" keys
    item_id = d.get("item_id", d.get("id", 0))
    children = [_item_from_dict(c) for c in d.get("children", [])]
    tele = None
    td = d.get("teleport_dest")
    if td:
        tele = _pos_from_dict(td)

    return ItemData(
        id=item_id,
        count=d.get("count", 0),
        action_id=d.get("action_id", 0),
        unique_id=d.get("unique_id", 0),
        text=d.get("text", ""),
        description=d.get("description", d.get("desc", "")),
        charges=d.get("charges", 0),
        house_door_id=d.get("house_door_id", d.get("door_id", 0)),
        depot_id=d.get("depot_id", 0),
        teleport_dest=tele,
        duration=d.get("duration", 0),
        decay_state=d.get("decay_state", d.get("decay", 0)),
        written_date=d.get("written_date", 0),
        written_by=d.get("written_by", ""),
        rune_charges=d.get("rune_charges", 0),
        sleeper_guid=d.get("sleeper_guid", 0),
        sleep_start=d.get("sleep_start", 0),
        children=children,
    )


def _tile_to_dict(tile: TileData, compact: bool = False) -> Dict[str, Any] | List[Any]:
    if compact and not tile.items and not tile.flags and not tile.house_id:
        return [tile.x, tile.y, tile.z, tile.ground_id]

    return {
        "x": tile.x,
        "y": tile.y,
        "z": tile.z,
        "ground_id": tile.ground_id,
        "items": [_item_to_dict(i, compact) for i in tile.items],
        "flags": int(tile.flags) if tile.flags else 0,
        "house_id": tile.house_id,
    }


def _tile_from_dict(d: Dict[str, Any] | List[Any]) -> TileData:
    if isinstance(d, (list, tuple)):
        # Compact: [x, y, z, ground_id]
        return TileData(x=d[0], y=d[1], z=d[2], ground_id=d[3] if len(d) > 3 else 0)

    items = [_item_from_dict(i) for i in d.get("items", [])]
    flags_raw = d.get("flags", 0)
    flags = TileFlag(flags_raw) if isinstance(flags_raw, int) else flags_raw
    return TileData(
        x=d["x"],
        y=d["y"],
        z=d["z"],
        ground_id=d.get("ground_id", 0),
        items=items,
        flags=flags,
        house_id=d.get("house_id", 0),
    )


def _town_to_dict(town: TownData) -> Dict[str, Any]:
    return {
        "town_id": town.id,
        "name": town.name,
        "temple_x": town.temple.x,
        "temple_y": town.temple.y,
        "temple_z": town.temple.z,
    }


def _town_from_dict(d: Dict[str, Any]) -> TownData:
    tid = d.get("town_id", d.get("id", 0))
    return TownData(
        id=tid,
        name=d.get("name", ""),
        temple=Position(
            x=d.get("temple_x", d.get("temple", {}).get("x", 0)),
            y=d.get("temple_y", d.get("temple", {}).get("y", 0)),
            z=d.get("temple_z", d.get("temple", {}).get("z", 7)),
        ),
    )


def _waypoint_to_dict(wp: WaypointData) -> Dict[str, Any]:
    return {"name": wp.name, "x": wp.pos.x, "y": wp.pos.y, "z": wp.pos.z}


def _waypoint_from_dict(d: Dict[str, Any]) -> WaypointData:
    pos = d.get("pos")
    if pos and isinstance(pos, dict):
        return WaypointData(name=d["name"], pos=Position(x=pos["x"], y=pos["y"], z=pos.get("z", 7)))
    return WaypointData(
        name=d["name"],
        pos=Position(x=d.get("x", 0), y=d.get("y", 0), z=d.get("z", 7)),
    )


def _spawn_to_dict(spawn: SpawnData) -> Dict[str, Any]:
    return {
        "x": spawn.x, "y": spawn.y, "z": spawn.z,
        "radius": spawn.radius,
        "monsters": list(spawn.monsters),
    }


def _spawn_from_dict(d: Dict[str, Any]) -> SpawnData:
    monsters = []
    for m in d.get("monsters", []):
        if isinstance(m, (list, tuple)):
            monsters.append(tuple(m))
        elif isinstance(m, dict):
            monsters.append((m["name"], m.get("count", 1), m.get("interval", 100)))
    return SpawnData(
        x=d["x"], y=d["y"], z=d["z"],
        radius=d.get("radius", 0),
        monsters=monsters,
    )


def _npc_spawn_to_dict(npc: NPCSpawnData) -> Dict[str, Any]:
    return {"x": npc.x, "y": npc.y, "z": npc.z, "npc_name": npc.npc_name, "direction": npc.direction}


def _npc_spawn_from_dict(d: Dict[str, Any]) -> NPCSpawnData:
    return NPCSpawnData(
        x=d["x"], y=d["y"], z=d["z"],
        npc_name=d.get("npc_name", ""),
        direction=d.get("direction", 0),
    )


def _house_to_dict(house: HouseData) -> Dict[str, Any]:
    return {
        "house_id": house.id,
        "name": house.name,
        "town_id": house.town_id,
        "rent": house.rent,
        "size": house.size,
        "tile_ids": list(house.tile_ids),
    }


def _house_from_dict(d: Dict[str, Any]) -> HouseData:
    hid = d.get("house_id", d.get("id", 0))
    return HouseData(
        id=hid,
        name=d.get("name", ""),
        rent=d.get("rent", 0),
        town_id=d.get("town_id", 0),
        size=d.get("size", 0),
        tile_ids=d.get("tile_ids", []),
    )


# ---------------------------------------------------------------------------
# MapJsonCodec
# ---------------------------------------------------------------------------

class MapJsonCodec:
    """Encode / decode :class:`MapData` to JSON-compatible dicts."""

    @staticmethod
    def encode(map_data: MapData, compact: bool = False) -> Dict[str, Any]:
        """Convert a :class:`MapData` to a JSON-compatible dictionary.

        Parameters
        ----------
        map_data : MapData
            The map to serialize.
        compact : bool
            If ``True``, tiles with no items/flags/house are stored as
            ``[x, y, z, ground_id]`` lists instead of full dicts.
        """
        result: Dict[str, Any] = {
            "version": _CODEC_VERSION,
            "width": map_data.width,
            "height": map_data.height,
            "description": map_data.description,
            "otbm_version": map_data.otbm_version,
            "otb_major_version": map_data.otb_major_version,
            "otb_minor_version": map_data.otb_minor_version,
            "tiles": [_tile_to_dict(t, compact) for t in map_data.tiles],
            "towns": [_town_to_dict(t) for t in map_data.towns],
            "waypoints": [_waypoint_to_dict(w) for w in map_data.waypoints],
            "spawns": [_spawn_to_dict(s) for s in map_data.spawns],
            "npc_spawns": [_npc_spawn_to_dict(n) for n in map_data.npc_spawns],
            "houses": [_house_to_dict(h) for h in map_data.houses],
        }
        # External file references
        if map_data.ext_spawn_file:
            result["ext_spawn_file"] = map_data.ext_spawn_file
        if map_data.ext_house_file:
            result["ext_house_file"] = map_data.ext_house_file
        if map_data.ext_spawn_npc_file:
            result["ext_spawn_npc_file"] = map_data.ext_spawn_npc_file
        return result

    @staticmethod
    def decode(data: Dict[str, Any]) -> MapData:
        """Convert a JSON-compatible dictionary back to a :class:`MapData`."""
        tiles = [_tile_from_dict(t) for t in data.get("tiles", [])]
        towns = [_town_from_dict(t) for t in data.get("towns", [])]
        waypoints = [_waypoint_from_dict(w) for w in data.get("waypoints", [])]
        spawns = [_spawn_from_dict(s) for s in data.get("spawns", [])]
        npc_spawns = [_npc_spawn_from_dict(n) for n in data.get("npc_spawns", [])]
        houses = [_house_from_dict(h) for h in data.get("houses", [])]

        return MapData(
            width=data.get("width", 2048),
            height=data.get("height", 2048),
            description=data.get("description", "Imported Map"),
            otbm_version=data.get("otbm_version", 2),
            otb_major_version=data.get("otb_major_version", 2),
            otb_minor_version=data.get("otb_minor_version", 7),
            tiles=tiles,
            towns=towns,
            waypoints=waypoints,
            spawns=spawns,
            npc_spawns=npc_spawns,
            houses=houses,
            ext_spawn_file=data.get("ext_spawn_file", ""),
            ext_house_file=data.get("ext_house_file", ""),
            ext_spawn_npc_file=data.get("ext_spawn_npc_file", ""),
        )

    @staticmethod
    def save(map_data: MapData, filepath: str, compact: bool = False, indent: int = 2) -> None:
        """Save a :class:`MapData` to a JSON file.

        Parameters
        ----------
        map_data : MapData
        filepath : str
            Output path (typically ``.json``).
        compact : bool
            Use compact tile format (lists instead of dicts).
        indent : int
            JSON indentation.  Set to ``None`` for minimal output.
        """
        data = MapJsonCodec.encode(map_data, compact=compact)
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

    @staticmethod
    def load(filepath: str) -> MapData:
        """Load a :class:`MapData` from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return MapJsonCodec.decode(data)

    @staticmethod
    def export_otbm(map_data: MapData, json_path: str, compact: bool = False) -> None:
        """Export a :class:`MapData` as JSON (convenience for ``save``)."""
        MapJsonCodec.save(map_data, json_path, compact=compact)

    @staticmethod
    def import_otbm(json_path: str, otbm_path: str) -> None:
        """Import a JSON file and write it as OTBM.

        Parameters
        ----------
        json_path : str
            Path to the source JSON file.
        otbm_path : str
            Path for the output ``.otbm`` file.
        """
        map_data = MapJsonCodec.load(json_path)
        writer = OTBMWriter(map_data)
        writer.save(otbm_path)
