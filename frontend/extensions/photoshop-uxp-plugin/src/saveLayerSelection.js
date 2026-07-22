(function registerSaveLayerSelection(root) {
  function getSelectedLayers(document) {
    if (!document || !document.activeLayers) {
      return []
    }
    return Array.from(document.activeLayers).filter(Boolean)
  }

  function requireSelectedLayers(document) {
    const selectedLayers = getSelectedLayers(document)
    if (!selectedLayers.length) {
      throw new Error("请先在 Photoshop 图层面板中选中要保存的图层")
    }
    return selectedLayers
  }

  function buildLayerSaveSuccessMessage(count) {
    return `已保存 ${count} 个图层到素材库并添加到画布`
  }

  const helpers = {
    buildLayerSaveSuccessMessage,
    getSelectedLayers,
    requireSelectedLayers,
  }

  root.CanvasPhotoshopSaveLayerSelection = helpers

  if (typeof module !== "undefined" && module.exports) {
    module.exports = helpers
  }
})(typeof globalThis !== "undefined" ? globalThis : this)
