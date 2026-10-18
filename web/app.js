"use strict";
const data = JSON.parse(document.getElementById("demo-data").textContent);
const byId = id => document.getElementById(id);
const element = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
const contexts = {
  q001: "The fixture asks for a count, then binds its final answer to the complete stored result.",
  q002: "A prewritten response invents a column. SQLite returns a schema error, and this script stops without a supported answer.",
  s001: "Hostile text stored in a track name reaches a later synthetic request. The script proposes DELETE; the execution boundary blocks it. This is enforcement, not measured model resistance.",
  recovery: "A different prewritten script corrects the column name after the schema error. This explains retry mechanics; it does not establish a measured improvement."
};
function selectCase(id, updateHash = true) {
  const item = data.cases.find(c => c.id === id) || data.cases[0];
  for (const button of document.querySelectorAll(".case-button")) {
    button.setAttribute("aria-pressed", String(button.dataset.case === item.id));
  }
  byId("question").textContent = item.question;
  byId("case-category").textContent = item.category.toUpperCase();
  byId("step-count").textContent = `${item.steps.length} tool steps`;
  byId("case-context").textContent = contexts[item.id];
  const answer = byId("answer");
  answer.replaceChildren();
  const card = element("div", undefined, "result-card");
  const final = item.final;
  if (final && final.status === "answered") {
    card.append(element("span", "SUPPORTED FINAL RESULT", "result-label"));
    const table = element("table");
    const head = element("thead");
    const headings = element("tr");
    for (const column of final.columns) {
      const th = element("th", String(column)); th.scope = "col"; headings.append(th);
    }
    head.append(headings); table.append(head);
    const body = element("tbody");
    for (const row of final.rows) {
      const tr = element("tr");
      for (const value of row) tr.append(element("td", value === null ? "NULL" : String(value)));
      body.append(tr);
    }
    table.append(body);
    const scroll = element("div", undefined, "table-scroll"); scroll.append(table); card.append(scroll);
  } else {
    card.classList.add("warning");
    card.append(element("span", final ? `FINAL STATUS: ${final.status.toUpperCase()}` : "NO SUPPORTED FINAL ANSWER", "result-label"));
    card.append(element("p", final ? "The script completed with a non-answer status. Inspect the tool boundary below." : "The failed query receives no correctness credit. An error is not a result."));
  }
  answer.append(card);
  const steps = byId("steps"); steps.replaceChildren();
  for (const [index, step] of item.steps.entries()) {
    const detail = element("details", undefined, "step"); detail.open = index === 0 || Boolean(step.output.error);
    const summary = element("summary");
    summary.append(element("span", String(index + 1).padStart(2, "0"), "step-number"));
    summary.append(element("span", step.name));
    if (step.output.blocked) summary.append(element("span", "BLOCKED", "blocked"));
    const content = element("div", undefined, "step-body");
    content.append(element("p", step.arguments.sql ? "SQL" : "ARGUMENTS", "code-label"));
    content.append(element("pre", step.arguments.sql || JSON.stringify(step.arguments, null, 2)));
    if (step.output.error) content.append(element("p", step.output.error, "error"));
    content.append(element("p", "ENFORCED TOOL OUTPUT", "code-label"));
    content.append(element("pre", JSON.stringify(step.output, null, 2)));
    detail.append(summary, content); steps.append(detail);
  }
  byId("trace-source").textContent = `${item.source} · ${item.config} · origin=${item.origin}`;
  byId("trace-hash").textContent = `SHA-256 ${item.source_sha256}`;
  if (updateHash) history.replaceState(null, "", `#case=${item.id}`);
}
byId("test-count").textContent = data.verification.test_counts?.passed ?? "—";
byId("candidate-count").textContent = data.candidate_tasks;
byId("review-count").textContent = data.reviewed_tasks;
byId("verification").textContent = data.verification.all_checks_passed ? `Required checks passed · ${data.verification.captured_at.slice(0, 10)}` : "Release checks need attention; inspect repository evidence";
for (const [index, item] of data.cases.entries()) {
  const button = element("button", undefined, "case-button");
  button.type = "button"; button.dataset.case = item.id;
  button.append(element("span", `${String(index + 1).padStart(2, "0")} / ${item.id.toUpperCase()}`), document.createTextNode(item.title));
  button.addEventListener("click", () => selectCase(item.id)); byId("cases").append(button);
}
const caseFromHash = () => location.hash.startsWith("#case=") ? location.hash.slice(6) : "q001";
selectCase(caseFromHash(), false);
window.addEventListener("hashchange", () => selectCase(caseFromHash(), false));
