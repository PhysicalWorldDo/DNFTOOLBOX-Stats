const state = {
  payload: null,
  rows: [],
  selected: null,
};

const numberFormatter = new Intl.NumberFormat("zh-CN");

const elements = {
  lastUpdated: document.querySelector("#lastUpdated"),
  totalDownloads: document.querySelector("#totalDownloads"),
  dailyDownloads: document.querySelector("#dailyDownloads"),
  toolCount: document.querySelector("#toolCount"),
  issueCount: document.querySelector("#issueCount"),
  topDaily: document.querySelector("#topDaily"),
  topTotal: document.querySelector("#topTotal"),
  searchInput: document.querySelector("#searchInput"),
  categoryFilter: document.querySelector("#categoryFilter"),
  statusFilter: document.querySelector("#statusFilter"),
  statsTable: document.querySelector("#statsTable"),
  detailPanel: document.querySelector("#detailPanel"),
  issuesList: document.querySelector("#issuesList"),
};

async function boot() {
  try {
    const response = await fetch("./stats-latest.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    state.payload = await response.json();
    state.rows = Array.isArray(state.payload.rows) ? state.payload.rows : [];
    state.selected = state.rows[0] || null;
    render();
  } catch (error) {
    elements.statsTable.innerHTML = `<tr><td colspan="7" class="empty">统计数据加载失败: ${escapeHtml(error.message)}</td></tr>`;
  }
}

function render() {
  renderSummary();
  renderRankList(elements.topDaily, state.payload.summary.top_daily || [], "daily");
  renderRankList(elements.topTotal, state.payload.summary.top_total || [], "total");
  renderCategoryOptions();
  renderRows();
  renderIssues();
  renderDetails(state.selected);
}

function renderSummary() {
  const summary = state.payload.summary || {};
  elements.lastUpdated.textContent = `最后更新: ${summary.generated_at || "--"}`;
  elements.totalDownloads.textContent = formatNumber(summary.total_downloads);
  elements.dailyDownloads.textContent = `+${formatNumber(summary.daily_downloads)}`;
  elements.toolCount.textContent = formatNumber(summary.tool_count);
  elements.issueCount.textContent = formatNumber(summary.issue_count);
}

function renderRankList(target, rows, mode) {
  if (!rows.length) {
    target.innerHTML = `<li class="empty">暂无数据</li>`;
    return;
  }
  target.innerHTML = rows
    .map((row) => {
      const value = mode === "daily" ? `+${formatNumber(row.daily_delta)}` : formatNumber(row.downloads);
      return `<li><strong>${escapeHtml(row.name)} ${escapeHtml(row.version)}</strong> <em>${value}</em></li>`;
    })
    .join("");
}

function renderCategoryOptions() {
  const selected = elements.categoryFilter.value || "all";
  const categories = [...new Set(state.rows.map((row) => row.category).filter(Boolean))].sort();
  elements.categoryFilter.innerHTML = [
    `<option value="all">全部</option>`,
    ...categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(category)}</option>`),
  ].join("");
  elements.categoryFilter.value = categories.includes(selected) ? selected : "all";
}

function filteredRows() {
  const query = elements.searchInput.value.trim().toLowerCase();
  const category = elements.categoryFilter.value;
  const status = elements.statusFilter.value;
  return state.rows.filter((row) => {
    const haystack = `${row.name} ${row.tool_id} ${row.repo} ${row.asset}`.toLowerCase();
    return (
      (!query || haystack.includes(query)) &&
      (category === "all" || row.category === category) &&
      (status === "all" || row.status === status)
    );
  });
}

function renderRows() {
  const rows = filteredRows();
  if (!rows.length) {
    elements.statsTable.innerHTML = `<tr><td colspan="7" class="empty">暂无匹配数据</td></tr>`;
    return;
  }

  elements.statsTable.innerHTML = rows
    .map((row, index) => {
      const selected = row === state.selected ? " selected" : "";
      return `
        <tr class="${selected}" data-index="${state.rows.indexOf(row)}">
          <td>${index + 1}</td>
          <td>
            <span class="tool-name">${escapeHtml(row.name)}</span>
            <span class="tool-id">${escapeHtml(row.tool_id)}</span>
          </td>
          <td>${escapeHtml(row.category || "--")}</td>
          <td>${escapeHtml(row.version || "--")}</td>
          <td class="delta">+${formatNumber(row.daily_delta)}</td>
          <td>${formatNumber(row.downloads)}</td>
          <td>${statusBadge(row.status)}</td>
        </tr>
      `;
    })
    .join("");

  elements.statsTable.querySelectorAll("tr[data-index]").forEach((rowElement) => {
    rowElement.addEventListener("click", () => {
      state.selected = state.rows[Number(rowElement.dataset.index)];
      renderRows();
      renderDetails(state.selected);
    });
  });
}

function renderDetails(row) {
  if (!row) {
    elements.detailPanel.innerHTML = `<dd class="empty">暂无数据</dd>`;
    return;
  }
  const releaseUrl = row.repo && row.tag ? `https://github.com/${row.repo}/releases/tag/${encodeURIComponent(row.tag)}` : "";
  elements.detailPanel.innerHTML = [
    detail("工具 ID", row.tool_id),
    detail("分类", row.category),
    detail("版本", row.version),
    detail("渠道", row.channel),
    detail("今日新增", `+${formatNumber(row.daily_delta)}`),
    detail("总下载次数", formatNumber(row.downloads)),
    detail("GitHub 仓库", row.repo),
    detail("Release Tag", row.tag),
    detail("Asset", row.asset),
    detail("状态", row.status),
    detail("错误", row.error || "--"),
    detailLink("Release 页面", releaseUrl),
    detailLink("packageUrl", row.package_url),
  ].join("");
}

function renderIssues() {
  const issues = state.rows.filter((row) => row.status !== "ok");
  if (!issues.length) {
    elements.issuesList.innerHTML = `<li class="empty">暂无异常</li>`;
    return;
  }
  elements.issuesList.innerHTML = issues
    .slice(0, 20)
    .map((row) => `<li><strong>${escapeHtml(row.name)} ${escapeHtml(row.version)}</strong>: ${escapeHtml(row.error || row.status)}</li>`)
    .join("");
}

function detail(label, value) {
  return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value || "--")}</dd>`;
}

function detailLink(label, url) {
  if (!url) {
    return detail(label, "--");
  }
  return `<dt>${escapeHtml(label)}</dt><dd><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(url)}</a></dd>`;
}

function statusBadge(status) {
  const label = {
    ok: "正常",
    error: "失败",
    skipped: "跳过",
  }[status] || status || "--";
  return `<span class="status ${escapeHtml(status || "")}">${escapeHtml(label)}</span>`;
}

function formatNumber(value) {
  return numberFormatter.format(Number(value) || 0);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

elements.searchInput.addEventListener("input", renderRows);
elements.categoryFilter.addEventListener("change", renderRows);
elements.statusFilter.addEventListener("change", renderRows);

boot();
