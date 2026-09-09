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

function renderOffer(offer) {
  const a = document.createElement("a");
  a.className = "offer";
  a.href = offer.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";

  const badgeClass = offer.site === "jobscz" ? "badge-jobscz" : "badge-pracecz";
  const siteLabel = offer.site === "jobscz" ? "Jobs.cz" : "Prace.cz";

  const title = document.createElement("div");
  title.className = "offer-title";
  title.innerHTML = `<span class="badge ${badgeClass}">${siteLabel}</span>${escapeHtml(offer.title)}`;
  a.appendChild(title);

  const meta = document.createElement("div");
  meta.className = "offer-meta";
  const parts = [];
  if (offer.employer) parts.push(offer.employer);
  else parts.push("Neznámý zaměstnavatel");
  if (offer.salary) parts.push(offer.salary);
  meta.textContent = parts.join(" · ");
  a.appendChild(meta);

  return a;
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
