function renderInsightBars(node) {
  const labels = JSON.parse(node.dataset.labels || "[]");
  const values = JSON.parse(node.dataset.values || "[]");
  const max = Math.max(...values, 1);
  const escapeHtml = (value) =>
    String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

  node.innerHTML = labels
    .map((label, index) => {
      const value = values[index] || 0;
      const width = Math.max(4, Math.round((value / max) * 100));
      return `
        <div class="insight-row">
          <span class="insight-label">${escapeHtml(label)}</span>
          <span class="insight-track">
            <span class="insight-value" style="width: ${width}%"></span>
          </span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `;
    })
    .join("");
}

document.querySelectorAll(".insight-bars").forEach(renderInsightBars);
