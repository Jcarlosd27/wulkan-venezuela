function graphifyBars(node) {
  const labels = JSON.parse(node.dataset.labels || "[]");
  const values = JSON.parse(node.dataset.values || "[]");
  const max = Math.max(...values, 1);

  node.innerHTML = labels
    .map((label, index) => {
      const value = values[index] || 0;
      const width = Math.max(4, Math.round((value / max) * 100));
      return `
        <div class="graphify-row">
          <span class="graphify-label">${label}</span>
          <span class="graphify-track">
            <span class="graphify-value" style="width: ${width}%"></span>
          </span>
          <strong>${value}</strong>
        </div>
      `;
    })
    .join("");
}

document.querySelectorAll(".graphify-bars").forEach(graphifyBars);
