(function bootstrap() {
  const DEFAULT_SERVER_BASE_URL = "__API_BASE_URL__"
  const photoshop = require("photoshop")
  const { entrypoints, storage } = require("uxp")
  const saveLayerSelection = window.CanvasPhotoshopSaveLayerSelection

  const state = {
    token: localStorage.getItem("ps_plugin_token") || "",
    serverBaseUrl: localStorage.getItem("ps_plugin_server_base_url") || DEFAULT_SERVER_BASE_URL,
    currentProjectId: Number(localStorage.getItem("ps_plugin_project_id") || 0) || null,
    currentProjectTitle: localStorage.getItem("ps_plugin_project_title") || "",
    activeJob: null,
    pendingDialogJobId: null,
    jobPollTimer: null,
  }

  const loginView = document.getElementById("login-view")
  const projectsView = document.getElementById("projects-view")
  const assetsView = document.getElementById("assets-view")
  const loginButton = document.getElementById("login-button")
  const logoutButton = document.getElementById("logout-button")
  const projectLogoutButton = document.getElementById("project-logout-button")
  const refreshProjectsButton = document.getElementById("refresh-projects")
  const backProjectsButton = document.getElementById("back-projects")
  const accountInput = document.getElementById("account-input")
  const passwordInput = document.getElementById("password-input")
  const loginMessage = document.getElementById("login-message")
  const workspaceMessage = document.getElementById("workspace-message")
  const saveMessage = document.getElementById("save-message")
  const projectList = document.getElementById("project-list")
  const assetList = document.getElementById("asset-list")
  const currentProjectLabel = document.getElementById("current-project-label")
  const serviceUrlInput = document.getElementById("service-url-input")
  const jobDialog = document.getElementById("job-dialog")
  const jobDialogMessage = document.getElementById("job-dialog-message")
  const jobDialogCancel = document.getElementById("job-dialog-cancel")
  const jobDialogConfirm = document.getElementById("job-dialog-confirm")
  const statusDialog = document.getElementById("status-dialog")
  const statusDialogMessage = document.getElementById("status-dialog-message")
  const statusDialogClose = document.getElementById("status-dialog-close")

  function normalizeServerBaseUrl(value) {
    const normalized = String(value || "").trim().replace(/\/+$/, "")
    return normalized.replace(/\/api\/v1$/i, "") || DEFAULT_SERVER_BASE_URL
  }

  state.serverBaseUrl = normalizeServerBaseUrl(state.serverBaseUrl)
  serviceUrlInput.value = state.serverBaseUrl

  function setMessage(element, text, isError = false) {
    element.textContent = text || ""
    element.style.color = isError ? "#dc2626" : "#6b7280"
  }

  function clearCurrentProject() {
    state.currentProjectId = null
    state.currentProjectTitle = ""
    localStorage.removeItem("ps_plugin_project_id")
    localStorage.removeItem("ps_plugin_project_title")
    currentProjectLabel.textContent = "项目图片"
    assetList.innerHTML = ""
    setMessage(saveMessage, "")
  }

  function showSuccessDialog(message) {
    statusDialogMessage.textContent = message
    if (statusDialog.open) {
      statusDialog.close()
    }
    statusDialog.showModal()
  }

  function closeStatusDialog() {
    if (statusDialog.open) {
      statusDialog.close()
    }
  }

  function closeJobDialog() {
    if (jobDialog.open) {
      jobDialog.close()
    }
  }

  function showView(viewName) {
    loginView.classList.toggle("hidden", viewName !== "login")
    projectsView.classList.toggle("hidden", viewName !== "projects")
    assetsView.classList.toggle("hidden", viewName !== "assets")
    logoutButton.classList.toggle("hidden", viewName === "login")
  }

  function resolveUrl(url) {
    if (!url) {
      return ""
    }
    return url.startsWith("http") ? url : `${state.serverBaseUrl}${url}`
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(`${state.serverBaseUrl}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
        ...(options.headers || {}),
      },
    })
    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.detail || `Request failed: ${response.status}`)
    }
    return response.json()
  }

  function projectTitle(project) {
    return project.project_name || project.title || project.name || `项目 ${project.project_id || project.id}`
  }

  function projectId(project) {
    return project.project_id || project.id
  }

  function projectImageCount(project) {
    const value = project.image_count ?? project.asset_count ?? 0
    const count = Number(value)
    return Number.isFinite(count) ? count : 0
  }

  function renderProjects(projects) {
    const projectItems = Array.isArray(projects) ? projects : []
    projectList.innerHTML = ""
    if (!projectItems.length) {
      projectList.innerHTML = '<div class="empty-state">暂无项目</div>'
      return
    }

    projectItems.forEach((project) => {
      const button = document.createElement("button")
      button.type = "button"
      button.className = "project-card"

      const content = document.createElement("span")
      content.className = "project-content"

      const text = document.createElement("span")
      text.className = "project-title"
      text.textContent = `${projectTitle(project)}（图片数量：${projectImageCount(project)}）`

      content.appendChild(text)
      button.appendChild(content)
      button.addEventListener("click", () => void openProject(project))
      projectList.appendChild(button)
    })

    if (projectItems.length % 2 === 1) {
      const spacer = document.createElement("span")
      spacer.className = "project-spacer"
      projectList.appendChild(spacer)
    }
  }

  function renderAssets(assets) {
    const assetItems = Array.isArray(assets) ? assets : []
    assetList.innerHTML = ""
    if (!assetItems.length) {
      assetList.innerHTML = '<div class="empty-state">当前项目暂无图片</div>'
      return
    }

    assetItems.forEach((asset) => {
      const card = document.createElement("div")
      card.className = "asset-card"

      const imageWrap = document.createElement("div")
      imageWrap.className = "asset-thumb"
      const image = document.createElement("img")
      image.src = resolveUrl(asset.url)
      image.alt = asset.project_name || "项目图片"
      imageWrap.appendChild(image)

      const button = document.createElement("button")
      button.type = "button"
      button.className = "primary-button"
      button.textContent = "添加到 PS"
      button.addEventListener("click", () => void addAssetToPhotoshop(asset))

      card.appendChild(imageWrap)
      card.appendChild(button)
      assetList.appendChild(card)
    })
  }

  async function loadProjects() {
    setMessage(workspaceMessage, "")
    const projects = await apiFetch("/api/v1/assets/projects?asset_type=image&limit=100")
    renderProjects(projects)
  }

  async function openProject(project) {
    state.currentProjectId = projectId(project)
    state.currentProjectTitle = projectTitle(project)
    localStorage.setItem("ps_plugin_project_id", String(state.currentProjectId))
    localStorage.setItem("ps_plugin_project_title", state.currentProjectTitle)
    currentProjectLabel.textContent = state.currentProjectTitle
    showView("assets")
    await loadProjectAssets(state.currentProjectId)
  }

  async function loadProjectAssets(projectId) {
    setMessage(saveMessage, "")
    const assets = await apiFetch(`/api/v1/projects/${projectId}/assets?asset_type=image&limit=100`)
    renderAssets(assets || [])
  }

  async function pollPendingJobs() {
    if (!state.token) {
      return
    }
    try {
      const jobs = await apiFetch("/api/v1/photoshop-edit-jobs/pending")
      const firstPending = (jobs || []).find((job) => job.status === "pending")
      if (firstPending && state.pendingDialogJobId !== firstPending.id) {
        state.pendingDialogJobId = firstPending.id
        jobDialogMessage.textContent = `检测到新的 PS 编辑任务 ${firstPending.source_canvas_item_id}，是否添加到 Photoshop？`
        jobDialog.showModal()
        jobDialogCancel.onclick = () => void cancelJob(firstPending)
        jobDialogConfirm.onclick = () => void importJobIntoPhotoshop(firstPending)
      }
    } catch (error) {
      setMessage(workspaceMessage, error.message || "轮询任务失败", true)
    }
  }

  function startJobPolling() {
    if (state.jobPollTimer) {
      clearInterval(state.jobPollTimer)
    }
    void pollPendingJobs()
    state.jobPollTimer = setInterval(() => {
      void pollPendingJobs()
    }, 10000)
  }

  async function importJobIntoPhotoshop(job) {
    try {
      const claimedJob = await apiFetch(`/api/v1/photoshop-edit-jobs/${job.id}/claim`, { method: "POST" })
      closeJobDialog()
      state.activeJob = claimedJob
      state.currentProjectId = claimedJob.project_id
      state.currentProjectTitle = `项目 ${claimedJob.project_id}`
      localStorage.setItem("ps_plugin_project_id", String(claimedJob.project_id))
      localStorage.setItem("ps_plugin_project_title", state.currentProjectTitle)
      await importImageUrlIntoPhotoshop(claimedJob.svg_url, `job-${claimedJob.id}.png`)
      setMessage(saveMessage, "已添加到 Photoshop")
    } catch (error) {
      await photoshop.app.showAlert(error.message || "导入失败")
    }
  }

  async function cancelJob(job) {
    try {
      await apiFetch(`/api/v1/photoshop-edit-jobs/${job.id}/cancel`, { method: "POST" })
      closeJobDialog()
      if (state.pendingDialogJobId === job.id) {
        state.pendingDialogJobId = null
      }
    } catch (error) {
      await photoshop.app.showAlert(error.message || "取消任务失败")
    }
  }

  async function addAssetToPhotoshop(asset) {
    try {
      await importImageUrlIntoPhotoshop(asset.url, `asset-${asset.id || Date.now()}.png`)
      setMessage(saveMessage, "已添加到 Photoshop")
    } catch (error) {
      setMessage(saveMessage, error.message || "添加到 PS 失败", true)
    }
  }

  async function importImageUrlIntoPhotoshop(imageUrl, fileName = `canvas-image-${Date.now()}.png`) {
    if (!imageUrl) {
      throw new Error("图片地址为空")
    }

    const response = await fetch(resolveUrl(imageUrl))
    if (!response.ok) {
      throw new Error(`下载图片失败：${response.status}`)
    }
    const bytes = await response.arrayBuffer()
    const tempFolder = await storage.localFileSystem.getTemporaryFolder()
    const tempFile = await tempFolder.createFile(fileName, { overwrite: true })
    await tempFile.write(bytes, { format: storage.formats.binary })
    const token = await storage.localFileSystem.createSessionToken(tempFile)

    await photoshop.core.executeAsModal(async () => {
      await photoshop.action.batchPlay([
        {
          _obj: "placeEvent",
          null: {
            _path: token,
            _kind: "local",
          },
          linked: true,
        },
      ], {})
      if (photoshop.app.bringToFront) {
        photoshop.app.bringToFront()
      }
    }, { commandName: "Import Canvas Image" })
  }

  async function uploadPngFile(projectId, tempFile, fileName) {
    const fileBuffer = await tempFile.read({ format: storage.formats.binary })
    const formData = new FormData()
    formData.append("file", new Blob([fileBuffer], { type: "image/png" }), fileName)
    const response = await fetch(`${state.serverBaseUrl}/api/v1/projects/${projectId}/upload/image`, {
      method: "POST",
      headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
      body: formData,
    })
    const data = await response.json()
    if (!response.ok) {
      throw new Error(data.detail || "上传保存结果失败")
    }
    return data.url
  }

  async function closeTemporaryDocument(document) {
    if (document?.closeWithoutSaving) {
      await document.closeWithoutSaving()
    }
  }

  async function exportLayerToPng(projectId, sourceDocument, layer, index) {
    const tempFolder = await storage.localFileSystem.getTemporaryFolder()
    const tempFile = await tempFolder.createFile(`ps-layer-save-${Date.now()}-${index + 1}.png`, { overwrite: true })
    if (!sourceDocument.saveAs?.png) {
      throw new Error("当前 Photoshop 版本缺少 PNG 导出能力")
    }

    let exportSize = {
      width: Math.max(1, Math.round(Number(sourceDocument.width) || 1024)),
      height: Math.max(1, Math.round(Number(sourceDocument.height) || 1024)),
    }

    await photoshop.core.executeAsModal(async () => {
      const tempDocument = await photoshop.app.createDocument({
        width: sourceDocument.width,
        height: sourceDocument.height,
        resolution: sourceDocument.resolution || 72,
        mode: "RGBColorMode",
        fill: "transparent",
      })
      try {
        await layer.duplicate(tempDocument)
        if (tempDocument.trim && photoshop.constants?.TrimType?.TRANSPARENT) {
          await tempDocument.trim(photoshop.constants.TrimType.TRANSPARENT)
        }
        await tempDocument.saveAs.png(tempFile, { quality: 32 }, true)
        exportSize = {
          width: Math.max(1, Math.round(Number(tempDocument.width) || exportSize.width)),
          height: Math.max(1, Math.round(Number(tempDocument.height) || exportSize.height)),
        }
      } finally {
        await closeTemporaryDocument(tempDocument)
      }
    }, { commandName: "Save Canvas Layer" })

    const url = await uploadPngFile(projectId, tempFile, `ps-layer-${index + 1}.png`)
    return {
      url,
      width: exportSize.width,
      height: exportSize.height,
    }
  }

  async function exportSelectedLayersToPngs(projectId) {
    const document = photoshop.app.activeDocument
    if (!document) {
      throw new Error("当前没有可保存的文档")
    }
    const selectedLayers = saveLayerSelection.requireSelectedLayers(document)
    const results = []
    for (let index = 0; index < selectedLayers.length; index += 1) {
      results.push(await exportLayerToPng(projectId, document, selectedLayers[index], index))
    }
    return results
  }

  async function saveCurrentDocumentToLibrary() {
    if (!state.currentProjectId) {
      await photoshop.app.showAlert("请先在插件中打开一个项目")
      return
    }

    try {
      const results = await exportSelectedLayersToPngs(state.currentProjectId)
      for (let index = 0; index < results.length; index += 1) {
        const result = results[index]
        if (state.activeJob?.id && results.length === 1) {
          await apiFetch(`/api/v1/photoshop-edit-jobs/${state.activeJob.id}/save`, {
            method: "POST",
            body: JSON.stringify({
              result_url: result.url,
              width: result.width,
              height: result.height,
              name: "PS添加",
              target_project_id: state.currentProjectId,
            }),
          })
          state.activeJob = null
          continue
        }
        await apiFetch(`/api/v1/projects/${state.currentProjectId}/photoshop-plugin/save`, {
          method: "POST",
          body: JSON.stringify({
            result_url: result.url,
            width: result.width,
            height: result.height,
          }),
        })
      }
      showSuccessDialog(saveLayerSelection.buildLayerSaveSuccessMessage(results.length))
      if (!assetsView.classList.contains("hidden")) {
        await loadProjectAssets(state.currentProjectId)
      }
    } catch (error) {
      await photoshop.app.showAlert(error.message || "保存失败")
    }
  }

  async function login() {
    try {
      state.serverBaseUrl = normalizeServerBaseUrl(serviceUrlInput.value)
      serviceUrlInput.value = state.serverBaseUrl
      const payload = await apiFetch("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({
          account: accountInput.value.trim(),
          password: passwordInput.value,
        }),
      })
      state.token = payload.access_token
      localStorage.setItem("ps_plugin_token", state.token)
      localStorage.setItem("ps_plugin_server_base_url", state.serverBaseUrl)
      setMessage(loginMessage, "")
      showView("projects")
      await loadProjects()
      startJobPolling()
    } catch (error) {
      setMessage(loginMessage, error.message || "登录失败", true)
    }
  }

  function logout() {
    localStorage.removeItem("ps_plugin_token")
    localStorage.removeItem("ps_plugin_project_id")
    localStorage.removeItem("ps_plugin_project_title")
    if (state.jobPollTimer) {
      clearInterval(state.jobPollTimer)
      state.jobPollTimer = null
    }
    state.token = ""
    state.currentProjectId = null
    state.currentProjectTitle = ""
    state.activeJob = null
    state.pendingDialogJobId = null
    showView("login")
    setMessage(saveMessage, "")
    setMessage(workspaceMessage, "")
  }

  loginButton.addEventListener("click", () => void login())
  logoutButton.addEventListener("click", logout)
  projectLogoutButton.addEventListener("click", logout)
  refreshProjectsButton.addEventListener("click", () => void loadProjects())
  statusDialogClose.addEventListener("click", closeStatusDialog)
  backProjectsButton.addEventListener("click", () => {
    clearCurrentProject()
    showView("projects")
    void loadProjects()
  })

  entrypoints.setup({
    commands: {
      "save-to-canvas-library": () => {
        void saveCurrentDocumentToLibrary()
      },
    },
    panels: {
      "canvas-photoshop-panel": {
        show() {},
      },
    },
  })

  window.saveCurrentDocumentToLibrary = saveCurrentDocumentToLibrary

  if (state.token) {
    showView("projects")
    void loadProjects()
    startJobPolling()
  } else {
    showView("login")
  }
}())
