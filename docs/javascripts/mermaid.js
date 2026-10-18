/* Mermaid integration with automatic dark/light theme matching */
function initMermaid() {
  if (typeof mermaid === "undefined") return;
  const isDark = document.body.getAttribute("data-md-color-scheme") === "slate";
  mermaid.initialize({
    startOnLoad: false,
    theme: isDark ? "dark" : "default",
    securityLevel: "loose",
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
  });
  mermaid.run({
    querySelector: ".mermaid"
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initMermaid);
} else {
  initMermaid();
}
