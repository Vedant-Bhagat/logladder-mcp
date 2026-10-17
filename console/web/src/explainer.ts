// Explainer markdown: CommonMark via marked, sanitised by DOMPurify, then [R-0042] tokens become receipt chips.
import DOMPurify from "dompurify";
import { marked } from "marked";
import { icon } from "./icons";

const RECEIPT_TOKEN = /\[(R-\d{4,})\]/g;

export function receiptChip(id: string, known: boolean): HTMLButtonElement {
  const b = document.createElement("button");
  b.type = "button";
  b.className = known ? "chip" : "chip unknown";
  b.dataset.receipt = id;
  b.title = known ? `Open receipt ${id}` : `Receipt ${id} was not sent with this explanation`;
  b.innerHTML = `${icon("receipt")}<span>${id}</span>`;
  return b;
}

export function renderMarkdown(target: HTMLElement, markdown: string, knownIds: Set<string>): void {
  const html = marked.parse(markdown ?? "", { async: false, gfm: true, breaks: false }) as string;
  target.innerHTML = DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest("code, pre") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const hits: Text[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) if (RECEIPT_TOKEN.test((n as Text).data)) hits.push(n as Text);
  for (const node of hits) {
    const frag = document.createDocumentFragment();
    let last = 0;
    const text = node.data;
    for (const m of text.matchAll(RECEIPT_TOKEN)) {
      frag.append(text.slice(last, m.index));
      frag.append(receiptChip(m[1], knownIds.has(m[1])));
      last = m.index! + m[0].length;
    }
    frag.append(text.slice(last));
    node.replaceWith(frag);
  }
  RECEIPT_TOKEN.lastIndex = 0;
}
