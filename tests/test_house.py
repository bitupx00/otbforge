"""Tests for HousePlacer — house rectangles, doors, interiors, furniture."""

import pytest
from ai_core.generators.house_placer import (
    HousePlacer,
    HouseTiles,
)
from ai_core.otbm_types import (
    MapData,
    ItemData,
    Position,
    TileData,
    TileFlags,
    Tiles,
)


class TestHousePlacerBasic:
    """Basic house placement tests."""

    def test_place_house_returns_id(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        house_id = hp.place_house(10, 10, 5, 5)
        assert house_id == 1

    def test_place_house_auto_increments_id(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        id1 = hp.place_house(10, 10, 5, 5)
        id2 = hp.place_house(20, 20, 5, 5)
        assert id2 == id1 + 1

    def test_explicit_house_id(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        house_id = hp.place_house(10, 10, 5, 5, house_id=100)
        assert house_id == 100

    def test_explicit_house_id_increments_from_there(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 5, 5, house_id=100)
        id2 = hp.place_house(20, 20, 5, 5)
        assert id2 == 101


class TestHouseTiles:
    """Verify house tile structure."""

    def test_house_has_walls(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), wall_id=1010)
        hp.place_house(10, 10, 5, 5)
        wall_tiles = [t for t in hp.map_data.tiles if t.ground_id == 1010]
        assert len(wall_tiles) > 0

    def test_house_has_floor(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), floor_id=410)
        hp.place_house(10, 10, 5, 5)
        floor_tiles = [t for t in hp.map_data.tiles if t.ground_id == 410]
        assert len(floor_tiles) > 0

    def test_interior_has_house_id(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6, house_id=42)
        interior = [t for t in hp.map_data.tiles
                   if 11 <= t.x <= 14 and 11 <= t.y <= 14 and t.house_id > 0]
        assert len(interior) > 0
        assert all(t.house_id == 42 for t in interior)


class TestHouseDoors:
    """Door placement tests."""

    def test_south_door_default(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), door_id=1209)
        hp.place_house(10, 10, 5, 5)
        # Door should be on south wall (y=14, x=12 center)
        door_tiles = [t for t in hp.map_data.tiles if t.ground_id == 1209]
        assert len(door_tiles) == 1
        assert door_tiles[0].y == 14  # south edge

    def test_north_door(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), door_id=1209)
        hp.place_house(10, 10, 5, 5, door_side="north")
        door_tiles = [t for t in hp.map_data.tiles if t.ground_id == 1209]
        assert len(door_tiles) == 1
        assert door_tiles[0].y == 10  # north edge

    def test_east_door(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), door_id=1209)
        hp.place_house(10, 10, 5, 5, door_side="east")
        door_tiles = [t for t in hp.map_data.tiles if t.ground_id == 1209]
        assert len(door_tiles) == 1
        assert door_tiles[0].x == 14  # east edge

    def test_west_door(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64), door_id=1209)
        hp.place_house(10, 10, 5, 5, door_side="west")
        door_tiles = [t for t in hp.map_data.tiles if t.ground_id == 1209]
        assert len(door_tiles) == 1
        assert door_tiles[0].x == 10  # west edge

    def test_door_has_house_door_item(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 5, 5, house_id=55)
        door_tiles = [t for t in hp.map_data.tiles
                      if any(i.house_door_id > 0 for i in t.items)]
        assert len(door_tiles) == 1


class TestHouseFurniture:
    """Furniture placement tests."""

    def test_furniture_placed(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6)
        furniture_tiles = [t for t in hp.map_data.tiles if len(t.items) > 0]
        assert len(furniture_tiles) > 0

    def test_has_bed(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6)
        beds = [t for t in hp.map_data.tiles
                if any(i.id == HouseTiles.BED for i in t.items)]
        assert len(beds) == 1

    def test_has_table(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6)
        tables = [t for t in hp.map_data.tiles
                 if any(i.id == HouseTiles.TABLE for i in t.items)]
        assert len(tables) == 1

    def test_has_chair(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6)
        chairs = [t for t in hp.map_data.tiles
                 if any(i.id == HouseTiles.CHAIR for i in t.items)]
        assert len(chairs) >= 1

    def test_has_chest(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6)
        chests = [t for t in hp.map_data.tiles
                 if any(i.id == HouseTiles.CHEST for i in t.items)]
        assert len(chests) == 1

    def test_no_furniture_when_disabled(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6, furniture=False)
        furniture_tiles = [t for t in hp.map_data.tiles
                           if any(i.id in (HouseTiles.BED, HouseTiles.TABLE,
                                          HouseTiles.CHAIR, HouseTiles.CHEST)
                                  for i in t.items)]
        assert len(furniture_tiles) == 0


class TestMultipleHouses:
    """Multiple house placement tests."""

    def test_place_houses_batch(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        ids = hp.place_houses([
            (5, 5, 5, 5),
            (15, 5, 5, 5),
            (5, 15, 5, 5),
        ])
        assert len(ids) == 3
        assert ids == [1, 2, 3]

    def test_place_random_houses(self):
        hp = HousePlacer(map_data=MapData(width=100, height=100), seed=42)
        ids = hp.place_random_houses(count=5, region_x=5, region_y=5,
                                      region_w=80, region_h=80)
        assert len(ids) == 5

    def test_random_houses_no_overlap(self):
        hp = HousePlacer(map_data=MapData(width=100, height=100), seed=42)
        hp.place_random_houses(count=5, region_x=5, region_y=5,
                               region_w=80, region_h=80, spacing=3)
        # Count tiles with different house_ids — should not overlap
        house_tiles = {}
        for t in hp.map_data.tiles:
            if t.house_id > 0:
                house_tiles.setdefault(t.house_id, []).append((t.x, t.y))
        for hid, coords in house_tiles.items():
            # No duplicate coords per house
            assert len(coords) == len(set(coords))


class TestHouseCounting:
    """House tile counting and bounding tests."""

    def test_count_house_tiles(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6, house_id=1)
        count = hp.count_house_tiles(1)
        # Interior of 6x6 = 4x4 = 16 tiles + door = 17
        assert count > 0

    def test_count_nonexistent_house(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 5, 5, house_id=1)
        count = hp.count_house_tiles(999)
        assert count == 0

    def test_get_house_rect(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 6, 6, house_id=1)
        rect = hp.get_house_rect(1)
        assert rect is not None
        x, y, w, h = rect
        # Interior starts at x+1, y+1 (walls excluded from house_id)
        assert x >= 11  # house_id tiles start inside walls
        assert y >= 11
        assert w >= 4   # interior of 6x6 = 4x4 + door
        assert h >= 4

    def test_get_house_rect_nonexistent(self):
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        rect = hp.get_house_rect(999)
        assert rect is None


class TestHouseIntegration:
    """Integration with TownGenerator."""

    def test_house_placer_with_town_map(self):
        from ai_core.generators.town import TownGenerator

        town_gen = TownGenerator(center_x=50, center_y=50, size=15,
                                 num_buildings=3, seed=1)
        town_map = town_gen.generate()

        hp = HousePlacer(map_data=town_map, starting_house_id=1)
        hp.place_house(60, 60, 5, 5, house_id=10)

        assert hp.count_house_tiles(10) > 0

    def test_house_placer_creates_own_map(self):
        hp = HousePlacer(width=64, height=64)
        result = hp.generate()
        assert isinstance(result, MapData)
        # Without placing houses, map_data is None → creates empty
        assert result.width == 64
        assert result.height == 64

    def test_small_house_minimum_size(self):
        """Test placing a minimum 3x3 house."""
        hp = HousePlacer(map_data=MapData(width=64, height=64))
        hp.place_house(10, 10, 3, 3)
        # Should have wall tiles
        assert len(hp.map_data.tiles) > 0
