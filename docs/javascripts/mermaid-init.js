// Render ```mermaid fences client-side (same parser family as GitHub).
// Works with and without Material's instant navigation.
function renderMermaid() {
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({ startOnLoad: true, securityLevel: "strict" });
    mermaid.run();
  }
}
if (typeof document$ !== "undefined") {
  document$.subscribe(renderMermaid);
} else {
  document.addEventListener("DOMContentLoaded", renderMermaid);
}
