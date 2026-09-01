const TAMY_BRAND = "Tamy";
const TAMY_REPO_URL = "https://github.com/mohamedamouseo-a11y/tamy";
const LEGACY_BRAND_RE = /\bAgent[\s-]+Zero\b/gi;

function tamyBrandText(value) {
  return typeof value === "string" ? value.replace(LEGACY_BRAND_RE, TAMY_BRAND) : value;
}

function tamyApplyBranding(root = document) {
  if (!root) return;
  const scope = root.nodeType === Node.ELEMENT_NODE || root.nodeType === Node.DOCUMENT_NODE || root.nodeType === Node.DOCUMENT_FRAGMENT_NODE
    ? root
    : root.parentElement;
  if (!scope) return;

  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest("script,style")) continue;
    const next = tamyBrandText(node.nodeValue);
    if (next !== node.nodeValue) node.nodeValue = next;
  }

  const elements = scope.querySelectorAll ? scope.querySelectorAll("*") : [];
  for (const el of elements) {
    for (const attr of ["title", "aria-label", "alt", "placeholder"]) {
      if (!el.hasAttribute?.(attr)) continue;
      const current = el.getAttribute(attr);
      const next = tamyBrandText(current);
      if (next !== current) el.setAttribute(attr, next);
    }
    if (el.tagName === "A") {
      const href = el.getAttribute("href") || "";
      if (href.includes("github.com/agent0ai/agent-zero") || href === "https://agent-zero.ai" || href === "https://www.agent-zero.ai") {
        el.setAttribute("href", TAMY_REPO_URL);
      }
    }
  }

  for (const card of scope.querySelectorAll?.(".discovery-cli-card") || []) card.remove();
  document.title = tamyBrandText(document.title || TAMY_BRAND);
}

const tamyObserver = new MutationObserver((records) => {
  for (const record of records) {
    if (record.type === "characterData") tamyApplyBranding(record.target.parentElement);
    for (const added of record.addedNodes || []) tamyApplyBranding(added);
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => tamyApplyBranding(document), { once: true });
} else {
  tamyApplyBranding(document);
}

tamyObserver.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
