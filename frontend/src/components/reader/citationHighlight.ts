import type { CitationFragment } from '../../types';

export const normalizeCitationText = (text: string) => text.normalize('NFKC').replace(/\s/gu, '');

export function clearCitationMarks(root: HTMLElement) {
  root.querySelectorAll('mark[data-citation]').forEach(mark => mark.replaceWith(...mark.childNodes));
  root.normalize();
}

/** Match the complete source unit before applying offsets: never highlight a
 * coincidental substring in a different paragraph or a differently ordered PDF. */
export function highlightCitation(root: HTMLElement, fragment: CitationFragment): HTMLElement | null {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const positions: { node: Text; start: number; end: number }[] = [];
  let text = '';
  let item: Node | null;
  while ((item = walker.nextNode())) {
    const node = item as Text;
    let offset = 0;
    for (const char of node.data) {
      const normalized = normalizeCitationText(char);
      for (const codepoint of normalized) {
        text += codepoint;
        positions.push({ node, start: offset, end: offset + char.length });
      }
      offset += char.length;
    }
  }
  // Python uses code-point offsets; Array.from keeps non-BMP text aligned.
  if (text !== normalizeCitationText(fragment.unit_text)) return null;
  const selected = positions.slice(fragment.start, fragment.end);
  if (!selected.length) return null;
  const ranges = new Map<Text, { start: number; end: number }>();
  for (const p of selected) {
    const existing = ranges.get(p.node);
    ranges.set(p.node, { start: existing?.start ?? p.start, end: p.end });
  }
  let first: HTMLElement | null = null;
  for (const [node, offsets] of ranges) {
    const range = document.createRange();
    range.setStart(node, offsets.start);
    range.setEnd(node, offsets.end);
    const mark = document.createElement('mark');
    mark.dataset.citation = 'true';
    mark.style.backgroundColor = 'rgba(250, 204, 21, 0.55)';
    mark.style.color = 'inherit';
    range.surroundContents(mark);
    first ??= mark;
  }
  return first;
}
