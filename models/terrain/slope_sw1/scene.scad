// Slope tile: south-west corner raised by 1 half-height step.
//
// Calibration target: landscape/grounds/texture-lightmap.png Image[1]
// (texture-lightmap.1.6, "sw1").
//
// World axes: +x = east, +y = north, +z = up.
// Tile corners in world coords:
//   NW = (-0.5, +0.5, 0)
//   NE = (+0.5, +0.5, 0)
//   SE = (+0.5, -0.5, 0)
//   SW = (-0.5, -0.5, 0)
// "sw1" raises SW by half-height (0.25 units); pak128 full-height = 0.5.

H_HALF = 0.25;

color([0.74, 0.74, 0.74])
polyhedron(
    points = [
        [-0.5,  0.5, 0],         // 0: NW
        [ 0.5,  0.5, 0],         // 1: NE
        [ 0.5, -0.5, 0],         // 2: SE
        [-0.5, -0.5, H_HALF],    // 3: SW (raised)
    ],
    faces = [[0, 1, 2, 3]]
);
