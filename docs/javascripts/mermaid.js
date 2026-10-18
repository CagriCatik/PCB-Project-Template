/* ==========================================================================
   Mermaid.js Integration & Theme Synchronization for PCB-Project-Template
   Uses async mermaid.render for bulletproof SVG generation across themes.
   ========================================================================== */

function getMermaidConfig(isDark) {
  const lightVariables = {
    primaryColor: '#f0fdf4',
    primaryBorderColor: '#059669',
    primaryTextColor: '#064e3b',
    lineColor: '#047857',
    secondaryColor: '#fef3c7',
    tertiaryColor: '#f1f5f9',
    clusterBkg: '#f8fafc',
    clusterBorder: '#cbd5e1',
    titleColor: '#064e3b',
    edgeLabelBackground: '#ffffff',
    nodeBorder: '#059669',
    mainBkg: '#f0fdf4',
    nodeTextColor: '#064e3b',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '13px'
  };

  const darkVariables = {
    primaryColor: '#091e16',
    primaryBorderColor: '#10b981',
    primaryTextColor: '#f8fafc',
    lineColor: '#10b981',
    secondaryColor: '#1f1b13',
    tertiaryColor: '#111822',
    clusterBkg: '#0c1218',
    clusterBorder: 'rgba(16, 185, 129, 0.28)',
    titleColor: '#f8fafc',
    edgeLabelBackground: '#111822',
    nodeBorder: '#10b981',
    mainBkg: '#091e16',
    nodeTextColor: '#f8fafc',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    fontSize: '13px'
  };

  return {
    startOnLoad: false,
    theme: 'base',
    themeVariables: isDark ? darkVariables : lightVariables,
    securityLevel: 'loose',
    flowchart: {
      htmlLabels: true,
      curve: 'linear',
      padding: 16,
      nodeSpacing: 35,
      rankSpacing: 42
    }
  };
}

function decodeHtml(text) {
  const txt = document.createElement('textarea');
  txt.innerHTML = text;
  return txt.value;
}

let renderSeq = 0;

async function renderMermaid() {
  if (typeof mermaid === 'undefined') return;

  const isDark = document.body.getAttribute('data-md-color-scheme') === 'slate';
  const elements = document.querySelectorAll('.mermaid');
  if (!elements.length) return;

  mermaid.initialize(getMermaidConfig(isDark));

  for (let i = 0; i < elements.length; i++) {
    const el = elements[i];
    if (!el.hasAttribute('data-mermaid-src')) {
      const raw = el.textContent || el.innerText || '';
      el.setAttribute('data-mermaid-src', decodeHtml(raw.trim()));
    }
    const sourceCode = el.getAttribute('data-mermaid-src');
    if (!sourceCode) continue;

    try {
      const id = 'mermaid-gen-' + (++renderSeq);
      const { svg } = await mermaid.render(id, sourceCode);
      el.innerHTML = svg;
    } catch (err) {
      console.warn('Mermaid render error:', err);
    }
  }
}

// Observe palette change on <body> (light/dark switch)
const paletteObserver = new MutationObserver((mutations) => {
  mutations.forEach((mutation) => {
    if (mutation.type === 'attributes' && mutation.attributeName === 'data-md-color-scheme') {
      renderMermaid();
    }
  });
});

if (document.body) {
  paletteObserver.observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });
}

// Initial render
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderMermaid);
} else {
  renderMermaid();
}
