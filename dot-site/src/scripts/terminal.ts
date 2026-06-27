/**
 * Animated terminal typewriter. For any `.terminal-window[data-animated="true"]`,
 * types `command` lines character-by-character and fades the rest in, once the
 * terminal scrolls into view. Honors prefers-reduced-motion (renders instantly).
 */
import { onceInView } from './intersection';

interface Line {
  type: string;
  text: string;
}

const TYPE_SPEED = 24; // ms per character for command lines
const LINE_GAP = 240; // ms between non-typed lines

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const reduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const STARTED = new WeakSet<Element>();

async function typeLine(el: HTMLElement, text: string): Promise<void> {
  el.textContent = '';
  el.style.opacity = '1';
  const caret = document.createElement('span');
  caret.className = 'caret';
  el.appendChild(caret);
  for (let i = 0; i < text.length; i++) {
    caret.insertAdjacentText('beforebegin', text[i]);
    await sleep(TYPE_SPEED);
  }
  caret.remove();
}

async function play(term: HTMLElement): Promise<void> {
  const body = term.querySelector<HTMLElement>('[data-terminal-body]');
  const raw = term.getAttribute('data-lines');
  if (!body || !raw) return;

  let lines: Line[];
  try {
    lines = JSON.parse(raw);
  } catch {
    return;
  }

  const lineEls = Array.from(body.querySelectorAll<HTMLElement>('.terminal-line'));

  if (reduced()) {
    lineEls.forEach((el, i) => {
      el.textContent = lines[i]?.text || ' ';
      el.style.opacity = '1';
    });
    return;
  }

  for (let i = 0; i < lineEls.length; i++) {
    const el = lineEls[i];
    const line = lines[i];
    if (!line) continue;
    if (line.type === 'command') {
      await typeLine(el, line.text);
      await sleep(LINE_GAP);
    } else {
      el.textContent = line.text || ' ';
      el.style.transition = 'opacity 300ms var(--easing)';
      el.style.opacity = '1';
      await sleep(line.text.trim() === '' ? 60 : LINE_GAP);
    }
  }
}

export function initAnimatedTerminals(): void {
  if (typeof document === 'undefined') return;
  const terminals = document.querySelectorAll<HTMLElement>(
    '.terminal-window[data-animated="true"]',
  );
  terminals.forEach((term) => {
    if (STARTED.has(term)) return;
    STARTED.add(term);
    onceInView(term, () => void play(term), { threshold: 0.4 });
  });
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAnimatedTerminals, { once: true });
  } else {
    initAnimatedTerminals();
  }
}
