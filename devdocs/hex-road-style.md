# Hex road style

What the hex road bakes aim for,
and how each tier is told apart.
The bakes live in `infrastructure/roads/`;
`tools/threed/way_preview.py` draws every tier as a small network
next to its pak128 cells,
which is the sheet to judge a change against.

## Goals

1. **Read at a glance.**
   A player looking at a town should see the road network first:
   where it runs, where it branches, where it ends.
   Roads have a crisp edge against grass,
   and the edge is a kerb or verge, never a ragged dither.
2. **Each tier is recognisable on its own,**
   by surface material first and markings second,
   colour alone is not enough.
3. **Pak128 at heart.**
   Same palette family, same pixel-art grain,
   same conventions (cobble sidewalks, white dashes, zebras),
   so a pak128 player feels at home.
4. **Hex-native geometry, pak128 shapes.**
   Bends are arcs, as in pak128's curve cells.
   Junctions have straight kerbs parallel to the tile edges
   and small bevelled corners;
   dead ends are cut square.
   Nothing reads as square art bent onto hexes.

A road cell is one flat surface shaded per pixel
from the distance to its centreline;
`tools/threed/way_surface.py` has the shapes,
`infrastructure/roads/road_params.py` the tiers below.

## Tiers

| Tier | Surface | Width | Edge | Markings |
| --- | --- | --- | --- | --- |
| road_030 | packed orange-brown earth, two dark ruts, grass in the middle | narrow | soft grass verge | none |
| cityroad_030 | sandy earth, ruts, scattered pebbles | medium | sandy verge | none |
| road_040 | brown stone setts | medium | cobble sidewalk, kerb line | none |
| road_050 | grey asphalt | medium | cobble sidewalk, kerb line | white dashed centre, zebras at junctions |
| road_055 | pinkish-grey gravel | narrow | soft verge | none |
| road_070 | asphalt | medium | dark tarmac rim, no sidewalk | white dashed centre |
| road_090 | asphalt | wide | dark rim, white solid edge lines | white dashed centre |
| highway_110 | darker asphalt | full | dark rim, white solid edge lines | double solid centre, dashed lane lines |
