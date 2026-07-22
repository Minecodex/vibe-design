const assert = require("node:assert/strict")

const {
  buildLayerSaveSuccessMessage,
  getSelectedLayers,
  requireSelectedLayers,
} = require("../src/saveLayerSelection.js")

assert.deepEqual(getSelectedLayers(null), [])
assert.deepEqual(getSelectedLayers({}), [])

const selectedLayers = [{ id: 1 }, { id: 2 }]
assert.deepEqual(getSelectedLayers({ activeLayers: selectedLayers }), selectedLayers)
assert.throws(
  () => requireSelectedLayers({ activeLayers: [] }),
  /请先在 Photoshop 图层面板中选中要保存的图层/,
)
assert.equal(requireSelectedLayers({ activeLayers: selectedLayers }).length, 2)
assert.equal(buildLayerSaveSuccessMessage(1), "已保存 1 个图层到素材库并添加到画布")
assert.equal(buildLayerSaveSuccessMessage(3), "已保存 3 个图层到素材库并添加到画布")

console.log("save layer selection helpers passed")
