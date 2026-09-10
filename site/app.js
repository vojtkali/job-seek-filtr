let REPO_INFO = { full_name: "vojtkali/job-seek-filtr", branch: "claude/job-offers-filtering-hfug64" };

async function main() {
  const metaEl = document.getElementById("meta");
  const runsEl = document.getElementById("runs");
  const warningsEl = document.getElementById("warnings");

  let payload;
  try {
    const res = await fetch("./data.json", { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    payload = await res.json();
  } catch (err) {
    metaEl.textContent = "Data se ještě nepodařilo načíst (data.json chybí nebo je poškozený).";
    return;
  }

  if (payload.repo) REPO_INFO = payload.repo;
  setupAddKeywordForm();
  setupBlacklistList(payload.blacklist || []);

  const runs = payload.runs || [];
  metaEl.textContent = runs.length
    ? `Naposledy kontrolováno: ${formatDateTime(payload.generated_at)}`
    : "Zatím žádná data - první běh scraperu ještě neproběhl.";

  const allWarnings = runs.flatMap((r) => r.warnings || []);
  if (allWarnings.length) {
    const seen = new Set();
    for (const w of allWarnings) {
      if (seen.has(w)) continue;
      seen.add(w);
      const div = document.createElement("div");
      div.className = "warning-banner";
      div.textContent = "⚠️ " + w;
      warningsEl.appendChild(div);
    }
  }

  const ordered = [...runs].reverse();
  for (const run of ordered) {
    const group = document.createElement("section");
    group.className = "run-group";

    const h2 = document.createElement("h2");
    h2.textContent = `${formatDate(run.run_at)} — ${run.offers.length} nových nabídek`;
    group.appendChild(h2);

    if (!run.offers.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "Žádné nové nabídky od minulé kontroly.";
      group.appendChild(p);
    } else {
      for (const offer of run.offers) {
        group.appendChild(renderOffer(offer));
      }
    }
    runsEl.appendChild(group);
  }

  if (!ordered.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Zatím žádná historie běhů.";
    runsEl.appendChild(p);
  }
}

function setupAddKeywordForm() {
  const form = document.getElementById("add-keyword-form");
  const input = document.getElementById("add-keyword-input");
  const status = document.getElementById("add-keyword-status");
  if (!form || !input) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const term = input.value.trim();
    if (!term) return;
    blockTerm(term, status);
    input.value = "";
  });
}

function blacklistEditUrl() {
  return `https://github.com/${REPO_INFO.full_name}/edit/${encodeURIComponent(REPO_INFO.branch)}/config/blacklist.txt`;
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    return false;
  }
}

async function blockTerm(term, statusEl) {
  const copied = await copyToClipboard(term);
  window.open(blacklistEditUrl(), "_blank", "noopener,noreferrer");
  if (statusEl) {
    statusEl.textContent = copied
      ? `Zkopírováno: "${term}" — vlož ho na nový řádek do blacklist.txt, který se právě otevřel na GitHubu, a commitni.`
      : `Otevřel se blacklist.txt na GitHubu — přidej na nový řádek: "${term}" a commitni (kopírování do schránky se nepovedlo).`;
  }
}

async function unblockTerm(term, statusEl) {
  const copied = await copyToClipboard(term);
  window.open(blacklistEditUrl(), "_blank", "noopener,noreferrer");
  if (statusEl) {
    statusEl.textContent = copied
      ? `Zkopírováno: "${term}" — najdi a smaž tenhle řádek v blacklist.txt, který se právě otevřel na GitHubu, a commitni.`
      : `Otevřel se blacklist.txt na GitHubu — najdi a smaž řádek: "${term}" a commitni (kopírování do schránky se nepovedlo).`;
  }
}

function setupBlacklistList(blacklist) {
  const toggle = document.getElementById("blacklist-toggle");
  const list = document.getElementById("blacklist-list");
  if (!toggle || !list) return;

  toggle.textContent = `Zobrazit blacklist (${blacklist.length})`;

  toggle.addEventListener("click", () => {
    const willShow = list.hidden;
    list.hidden = !willShow;
    toggle.textContent = willShow
      ? `Skrýt blacklist (${blacklist.length})`
      : `Zobrazit blacklist (${blacklist.length})`;
    if (willShow && !list.dataset.rendered) {
      renderBlacklistList(list, blacklist);
      list.dataset.rendered = "1";
    }
  });
}

function renderBlacklistList(container, blacklist) {
  if (!blacklist.length) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Blacklist je zatím prázdný.";
    container.appendChild(p);
    return;
  }
  for (const term of blacklist) {
    const row = document.createElement("div");
    row.className = "blacklist-row";

    const span = document.createElement("span");
    span.textContent = term;
    row.appendChild(span);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "block-btn";
    btn.textContent = "🗑 Odebrat";
    btn.addEventListener("click", () => {
      const status = document.getElementById("add-keyword-status");
      btn.textContent = "Zkopírováno ✓";
      unblockTerm(term, status);
      setTimeout(() => { btn.textContent = "🗑 Odebrat"; }, 3000);
    });
    row.appendChild(btn);

    container.appendChild(row);
  }
}

function renderOffer(offer) {
  const card = document.createElement("div");
  card.className = "offer";

  const a = document.createElement("a");
  a.className = "offer-link";
  a.href = offer.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";

  const SITE_META = {
    jobscz: { badge: "badge-jobscz", label: "Jobs.cz" },
    pracecz: { badge: "badge-pracecz", label: "Prace.cz" },
  };
  const meta_ = SITE_META[offer.site] || { badge: "badge-jobscz", label: offer.site };
  const badgeClass = meta_.badge;
  const siteLabel = meta_.label;

  const title = document.createElement("div");
  title.className = "offer-title";
  title.innerHTML = `<span class="badge ${badgeClass}">${siteLabel}</span>${escapeHtml(offer.title)}`;
  a.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "offer-meta";
  const parts = [];
  parts.push(offer.employer || "Neznámý zaměstnavatel");
  if (offer.salary) parts.push(offer.salary);
  if (offer.posted) parts.push(offer.posted);
  meta.textContent = parts.join(" · ");
  a.appendChild(meta);

  card.appendChild(a);

  if (offer.employer) {
    const actions = document.createElement("div");
    actions.className = "offer-actions";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "block-btn";
    btn.textContent = "🚫 Blokovat firmu";
    btn.addEventListener("click", () => {
      btn.textContent = "Zkopírováno ✓";
      blockTerm(offer.employer, null);
      setTimeout(() => { btn.textContent = "🚫 Blokovat firmu"; }, 3000);
    });
    actions.appendChild(btn);
    card.appendChild(actions);
  }

  return card;
}

function formatDate(iso) {
  if (!iso) return "?";
  const d = new Date(iso);
  return d.toLocaleDateString("cs-CZ", { weekday: "long", day: "numeric", month: "numeric", year: "numeric" });
}

function formatDateTime(iso) {
  if (!iso) return "?";
  const d = new Date(iso);
  return d.toLocaleString("cs-CZ");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

main();
