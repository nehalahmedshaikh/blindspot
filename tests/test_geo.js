"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const geo = require("../site/geo.js");

assert.deepEqual(
  geo.unwrapRing([[170, 0], [-170, 1], [-160, 2]]),
  [[170, 0], [190, 1], [200, 2]],
  "a ring crossing eastward must remain continuous"
);
assert.deepEqual(
  geo.unwrapRing([[-170, 0], [170, 1], [160, 2]]),
  [[-170, 0], [-190, 1], [-200, 2]],
  "a ring crossing westward must remain continuous"
);

const topology = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../site/assets/countries-110m.json"), "utf8")
);
const arcs = geo.topologyArcs(topology);
for (const geometry of topology.objects.countries.geometries) {
  const rendered = geo.pathFor(geometry, arcs);
  assert.ok(rendered.length > 0, `country ${geometry.id} must render`);
  for (const ring of geo.geometryRings(geometry, arcs)) {
    const continuous = geo.unwrapRing(ring);
    for (let index = 1; index < continuous.length; index += 1) {
      assert.ok(
        Math.abs(continuous[index][0] - continuous[index - 1][0]) <= 180,
        `country ${geometry.id} contains an unhandled antimeridian edge`
      );
    }
  }
}

console.log(`✓ antimeridian-safe paths for ${topology.objects.countries.geometries.length} map features`);
