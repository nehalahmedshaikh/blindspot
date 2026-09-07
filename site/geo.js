"use strict";

(function expose(root) {
  function topologyArcs(topology) {
    const [sx, sy] = topology.transform.scale;
    const [tx, ty] = topology.transform.translate;
    return topology.arcs.map(arc => {
      let x = 0;
      let y = 0;
      return arc.map(([dx, dy]) => {
        x += dx;
        y += dy;
        return [x * sx + tx, y * sy + ty];
      });
    });
  }

  function geometryRings(geometry, arcs) {
    const decode = index => index >= 0 ? arcs[index] : [...arcs[~index]].reverse();
    const ring = indexes => indexes.flatMap((index, position) => decode(index).slice(position ? 1 : 0));
    if (geometry.type === "Polygon") return geometry.arcs.map(ring);
    if (geometry.type === "MultiPolygon") return geometry.arcs.flatMap(polygon => polygon.map(ring));
    return [];
  }

  function unwrapRing(ring) {
    if (!ring.length) return [];
    const result = [[ring[0][0], ring[0][1]]];
    for (let index = 1; index < ring.length; index += 1) {
      let longitude = ring[index][0];
      const previous = result[index - 1][0];
      while (longitude - previous > 180) longitude -= 360;
      while (longitude - previous < -180) longitude += 360;
      result.push([longitude, ring[index][1]]);
    }
    return result;
  }

  function visibleCopies(ring) {
    const unwrapped = unwrapRing(ring);
    if (!unwrapped.length) return [];
    const longitudes = unwrapped.map(point => point[0]);
    const minimum = Math.min(...longitudes);
    const maximum = Math.max(...longitudes);
    return [-360, 0, 360]
      .filter(shift => maximum + shift >= -180 && minimum + shift <= 180)
      .map(shift => unwrapped.map(([longitude, latitude]) => [longitude + shift, latitude]));
  }

  function ringPath(ring, width, height) {
    return ring.map(([longitude, latitude], index) => {
      const x = (longitude + 180) / 360 * width;
      const y = (90 - latitude) / 180 * height;
      return `${index ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join("") + "Z";
  }

  function pathFor(geometry, arcs, width = 1000, height = 500) {
    return geometryRings(geometry, arcs)
      .flatMap(visibleCopies)
      .map(ring => ringPath(ring, width, height))
      .join("");
  }

  const api = { geometryRings, pathFor, topologyArcs, unwrapRing, visibleCopies };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.BlindspotGeo = api;
})(typeof window !== "undefined" ? window : globalThis);
