// Flat ground tile.
//
// Calibration target: landscape/grounds/texture-lightmap.png, Image[0]
// (texture-lightmap.0.14, "flat"). The reference diamond occupies the
// bottom half of the 128x128 tile (y=65..128, full width).
//
// One pak128 tile = 1 unit on each horizontal axis. Z=0 is ground level.

// Single quad (no thickness) so the side faces don't show.
color([0.74, 0.74, 0.74])
polyhedron(
    points = [
        [-0.5, -0.5, 0],
        [ 0.5, -0.5, 0],
        [ 0.5,  0.5, 0],
        [-0.5,  0.5, 0],
    ],
    faces = [[0, 1, 2, 3]]
);
