"""Esportazione dei risultati e dei report di audit."""

from __future__ import annotations

import csv
import html
import json
import time
from pathlib import Path
from typing import Iterable

from .providers.base import SearchResult

FORMATS = {
    "csv": "CSV (fogli di calcolo)",
    "json": "JSON (rielaborazione)",
    "md": "Markdown (documentazione)",
    "html": "HTML (report leggibile)",
}

_STAMP = "%d/%m/%Y %H:%M"


def _now() -> str:
    return time.strftime(_STAMP)


# ------------------------------------------------------------------ risultati
def results_to_csv(results: Iterable[SearchResult], path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["titolo", "url", "dominio", "tipo", "motore",
                         "pubblicato", "conformita", "estratto"])
        for item in results:
            writer.writerow([item.title, item.url, item.domain, item.filetype,
                             item.provider, item.published, item.compliance,
                             " ".join((item.snippet or "").split())])
    return path


def results_to_json(results: Iterable[SearchResult], path: str | Path,
                    query: str = "") -> Path:
    path = Path(path)
    payload = {
        "generato": _now(),
        "query": query,
        "risultati": [
            {
                "titolo": item.title, "url": item.url, "dominio": item.domain,
                "tipo": item.filetype, "motore": item.provider,
                "pubblicato": item.published, "estratto": item.snippet,
                "conformita": item.compliance, "verifiche": item.checks,
                "punteggio": item.score,
            }
            for item in results
        ],
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def results_to_markdown(results: Iterable[SearchResult], path: str | Path,
                        query: str = "", answer: str = "") -> Path:
    path = Path(path)
    items = list(results)
    lines = [
        "# Risultati DorkLab",
        "",
        "- **Query**: `%s`" % query,
        "- **Generato**: %s" % _now(),
        "- **Risultati**: %d" % len(items),
        "",
    ]
    if answer:
        lines += ["## Sintesi del motore agentico", "", answer, ""]
    lines += ["## Risultati", ""]
    for index, item in enumerate(items, start=1):
        lines.append("%d. [%s](%s)" % (index, item.title or item.url, item.url))
        details = []
        if item.filetype:
            details.append("tipo: `%s`" % item.filetype)
        if item.domain:
            details.append("dominio: `%s`" % item.domain)
        if item.compliance and item.compliance != "sconosciuto":
            details.append("vincoli: %s" % item.compliance)
        if details:
            lines.append("   - " + " · ".join(details))
        if item.snippet:
            lines.append("   - %s" % " ".join(item.snippet.split())[:300])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def results_to_html(results: Iterable[SearchResult], path: str | Path,
                    query: str = "", answer: str = "") -> Path:
    path = Path(path)
    items = list(results)
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            "<tr><td>{n}</td><td><a href='{url}' target='_blank' rel='noopener'>{title}</a>"
            "<div class='u'>{url}</div></td><td>{ft}</td><td>{dom}</td>"
            "<td class='c c-{cl}'>{cl}</td><td>{sn}</td></tr>".format(
                n=index,
                url=html.escape(item.url),
                title=html.escape(item.title or item.url),
                ft=html.escape(item.filetype or "-"),
                dom=html.escape(item.domain),
                cl=html.escape(item.compliance or "-"),
                sn=html.escape(" ".join((item.snippet or "").split())[:280]),
            )
        )
    answer_block = ("<section class='answer'><h2>Sintesi del motore</h2><p>%s</p></section>"
                    % html.escape(answer).replace("\n", "<br>")) if answer else ""
    path.write_text(_HTML_TEMPLATE.format(
        query=html.escape(query), generated=_now(), count=len(items),
        answer=answer_block, rows="\n".join(rows)), encoding="utf-8")
    return path


_HTML_TEMPLATE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Risultati DorkLab</title>
<style>
:root {{ color-scheme: light dark; --bg:#fbfbfd; --fg:#16181d; --mut:#6b7280;
  --line:#e3e5ea; --card:#fff; --acc:#3d7bff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14161a; --fg:#e8eaf0;
  --mut:#9aa1ad; --line:#2a2e36; --card:#1b1e24; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; padding:24px; background:var(--bg); color:var(--fg);
  font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.meta {{ color:var(--mut); margin-bottom:20px; font-size:13px; }}
.answer {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:14px 18px; margin-bottom:20px; }}
.answer h2 {{ font-size:15px; margin:0 0 8px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
th, td {{ text-align:left; padding:10px 12px; border-bottom:1px solid var(--line);
  vertical-align:top; }}
th {{ background:rgba(125,125,145,.08); font-size:12px; text-transform:uppercase;
  letter-spacing:.04em; color:var(--mut); }}
tr:last-child td {{ border-bottom:none; }}
a {{ color:var(--acc); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.u {{ color:var(--mut); font-size:12px; word-break:break-all; }}
.c {{ font-size:12px; font-weight:600; }}
.c-ok {{ color:#16a34a; }} .c-fuori {{ color:#dc2626; }} .c-parziale {{ color:#d97706; }}
</style></head><body>
<h1>Risultati DorkLab</h1>
<div class="meta"><code>{query}</code> &middot; {count} risultati &middot; {generated}</div>
{answer}
<table><thead><tr><th>#</th><th>Risultato</th><th>Tipo</th><th>Dominio</th>
<th>Vincoli</th><th>Estratto</th></tr></thead><tbody>
{rows}
</tbody></table>
</body></html>
"""


# ---------------------------------------------------------------- report audit
def audit_to_markdown(plan, path: str | Path, metadata: dict | None = None) -> Path:
    """Genera il report di un audit difensivo in Markdown."""
    path = Path(path)
    summary = plan.summary()
    lines = [
        "# Report di esposizione - %s" % plan.domain,
        "",
        "- **Dominio verificato**: `%s`" % plan.domain,
        "- **Data**: %s" % _now(),
        "- **Controlli eseguiti**: %d su %d" % (summary["eseguite"], summary["totali"]),
        "- **Controlli con risultati da verificare**: %d" % summary["con_risultati"],
        "",
        "> Report generato con DorkLab. Le query sono state eseguite esclusivamente",
        "> sul dominio autorizzato indicato sopra.",
        "",
    ]

    findings = plan.findings()
    if findings:
        lines += ["## Sintesi", "", "| Gravita' | Controllo | Risultati |", "|---|---|---|"]
        for item in sorted(findings, key=lambda q: q.severity):
            lines.append("| %s | %s | %d |" % (item.severity, item.check_label, item.hits))
        lines.append("")

    lines += ["## Dettaglio dei controlli", ""]
    seen_checks: set[str] = set()
    for item in plan.by_severity():
        if item.check_id not in seen_checks:
            seen_checks.add(item.check_id)
            lines += ["### %s (%s)" % (item.check_label, item.severity), "",
                      item.description, "", "**Perche' conta**: %s" % item.why, ""]
            if item.remediation:
                lines += ["**Come rimediare**", ""]
                lines += ["- %s" % step for step in item.remediation]
                lines.append("")
        marker = {"da eseguire": "[ ]", "nessuna esposizione": "[ok]",
                  "da verificare": "[!]", "errore": "[x]"}.get(item.status, "[ ]")
        lines.append("- %s `%s` - %s" % (marker, item.query, item.status))
        if item.hits:
            lines[-1] += " (%d risultati)" % item.hits
        if item.note:
            lines.append("  - nota: %s" % item.note)
        if item.error:
            lines.append("  - errore: %s" % item.error)
    lines.append("")

    if metadata:
        lines += ["## Note", ""]
        lines += ["- **%s**: %s" % (k, v) for k, v in metadata.items()]
        lines.append("")

    lines += [
        "## Avvertenza",
        "",
        "Un risultato non e' automaticamente una vulnerabilita': va verificato "
        "manualmente. L'assenza di risultati indica soltanto che il motore di "
        "ricerca non ha indicizzato nulla di corrispondente, non che il contenuto "
        "non sia raggiungibile.",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def audit_to_csv(plan, path: str | Path) -> Path:
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dominio", "controllo", "gravita", "query", "stato",
                         "risultati", "nota", "errore"])
        for item in plan.by_severity():
            writer.writerow([plan.domain, item.check_label, item.severity, item.query,
                             item.status, item.hits, item.note, item.error])
    return path


def audit_to_html(plan, path: str | Path) -> Path:
    path = Path(path)
    summary = plan.summary()
    blocks = []
    seen: set[str] = set()
    for item in plan.by_severity():
        if item.check_id not in seen:
            seen.add(item.check_id)
            steps = "".join("<li>%s</li>" % html.escape(s) for s in item.remediation)
            blocks.append(
                "<section class='check sev-{sev}'><h3>{label} "
                "<span class='badge'>{sev}</span></h3><p>{desc}</p>"
                "<p class='why'><strong>Perche' conta:</strong> {why}</p>"
                "<details><summary>Come rimediare</summary><ul>{steps}</ul></details>"
                "<ul class='queries' id='q-{cid}'></ul></section>".format(
                    sev=html.escape(item.severity), label=html.escape(item.check_label),
                    desc=html.escape(item.description), why=html.escape(item.why),
                    steps=steps, cid=html.escape(item.check_id)))
    rows = "".join(
        "<tr><td>{sev}</td><td>{label}</td><td><code>{q}</code></td>"
        "<td>{st}</td><td>{h}</td></tr>".format(
            sev=html.escape(i.severity), label=html.escape(i.check_label),
            q=html.escape(i.query), st=html.escape(i.status), h=i.hits)
        for i in plan.by_severity())

    path.write_text(_AUDIT_TEMPLATE.format(
        domain=html.escape(plan.domain), generated=_now(),
        done=summary["eseguite"], total=summary["totali"],
        findings=summary["con_risultati"], rows=rows,
        checks="".join(blocks)), encoding="utf-8")
    return path


_AUDIT_TEMPLATE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Esposizione - {domain}</title>
<style>
:root {{ color-scheme: light dark; --bg:#fbfbfd; --fg:#16181d; --mut:#6b7280;
  --line:#e3e5ea; --card:#fff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14161a; --fg:#e8eaf0;
  --mut:#9aa1ad; --line:#2a2e36; --card:#1b1e24; }} }}
body {{ margin:0; padding:24px; background:var(--bg); color:var(--fg);
  font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif; max-width:960px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.meta {{ color:var(--mut); font-size:13px; margin-bottom:22px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:28px;
  background:var(--card); border:1px solid var(--line); border-radius:10px; }}
th, td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); }}
th {{ font-size:12px; text-transform:uppercase; color:var(--mut); }}
code {{ font-size:12px; word-break:break-all; }}
.check {{ background:var(--card); border:1px solid var(--line); border-left-width:4px;
  border-radius:10px; padding:14px 18px; margin-bottom:14px; }}
.sev-critica {{ border-left-color:#c0392b; }} .sev-alta {{ border-left-color:#e67e22; }}
.sev-media {{ border-left-color:#f1c40f; }} .sev-info {{ border-left-color:#3d7bff; }}
.check h3 {{ font-size:15px; margin:0 0 6px; }}
.badge {{ font-size:11px; text-transform:uppercase; color:var(--mut); font-weight:600; }}
.why {{ color:var(--mut); font-size:13px; }}
summary {{ cursor:pointer; font-size:13px; font-weight:600; }}
</style></head><body>
<h1>Report di esposizione</h1>
<div class="meta"><strong>{domain}</strong> &middot; {generated} &middot;
{done}/{total} controlli eseguiti &middot; {findings} con risultati da verificare</div>
<table><thead><tr><th>Gravita'</th><th>Controllo</th><th>Query</th>
<th>Stato</th><th>Risultati</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Controlli e rimedi</h2>
{checks}
<p class="meta">Un risultato non e' automaticamente una vulnerabilita': va verificato
manualmente. L'assenza di risultati indica solo che il motore non ha indicizzato nulla
di corrispondente.</p>
</body></html>
"""
