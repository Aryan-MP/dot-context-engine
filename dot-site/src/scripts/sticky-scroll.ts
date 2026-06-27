/**
 * Product section controller.
 *
 * Desktop: a sticky left "orbit" panel whose active scene tracks which of the
 * three scrolling segments is in view. Each segment plays a one-shot animation
 * the first time it appears (file indexing, decision mining, context assembly).
 *
 * Mobile: the same three segments become a tabbed interface.
 */

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const reduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const INDEX_FILES = [
  'src/auth/middleware.ts',
  'src/payments/processor.ts',
  'src/api/routes.ts',
  'src/db/redis.ts',
  'src/events/sourcing.ts',
  'src/events/projections.ts',
  'src/workers/reconcile.ts',
  'src/lib/retry.ts',
  'src/lib/rate-limit.ts',
  'src/services/session.ts',
  'tests/payments.spec.ts',
  'docs/adr/0007-event-sourcing.md',
];

const COMMITS = [
  { sha: '9f2c1a', msg: 'chore: bump dependencies', hit: false },
  { sha: 'abc123', msg: 'Switch order state to event sourcing', hit: true },
  { sha: '77d0e2', msg: 'fix: flaky reconcile worker test', hit: false },
  { sha: 'def456', msg: 'Use Redis over Memcached for sessions', hit: true },
  { sha: '31bb9c', msg: 'style: run formatter', hit: false },
  { sha: 'ghi789', msg: 'Remove synchronous HTTP calls in checkout', hit: true },
  { sha: 'c4e88d', msg: 'docs: update README', hit: false },
];

const ASM_STEPS = [
  { label: '⟳ semantic search...', done: '✓ 20 chunks' },
  { label: '⟳ proximity scan...', done: '✓ 8 chunks' },
  { label: '⟳ recency check...', done: '✓ 5 chunks' },
  { label: '⟳ decision lookup...', done: '✓ 3 decisions' },
  { label: '⟳ dependency graph...', done: '✓ 12 nodes' },
];

function setActiveStage(root: HTMLElement, index: number): void {
  const stage = root.querySelector<HTMLElement>('[data-product-stage]');
  if (stage) stage.setAttribute('data-active', String(index));
  root.querySelectorAll<HTMLElement>('[data-scene]').forEach((scene) => {
    scene.classList.toggle('scene-active', scene.dataset.scene === String(index));
  });
}

async function playSegment1(root: HTMLElement): Promise<void> {
  const stream = root.querySelector<HTMLElement>('[data-idx-stream]');
  const bar = root.querySelector<HTMLElement>('[data-idx-bar]');
  const done = root.querySelector<HTMLElement>('[data-idx-done]');
  const pills = root.querySelectorAll<HTMLElement>('[data-idx-pill]');
  if (!stream) return;

  if (reduced()) {
    INDEX_FILES.slice(0, 4).forEach((f) => {
      const d = document.createElement('div');
      d.innerHTML = `<span class="text-green">✓</span> indexing ${f}`;
      stream.appendChild(d);
    });
    if (bar) bar.style.width = '100%';
    done?.classList.add('on');
    pills.forEach((p) => p.classList.add('visible'));
    return;
  }

  for (let i = 0; i < INDEX_FILES.length; i++) {
    const row = document.createElement('div');
    row.innerHTML = `<span class="text-green">✓</span> indexing ${INDEX_FILES[i]}`;
    stream.appendChild(row);
    stream.scrollTop = stream.scrollHeight;
    if (bar) bar.style.width = `${Math.round(((i + 1) / INDEX_FILES.length) * 100)}%`;
    await sleep(120);
  }
  done?.classList.add('on');
  await sleep(200);
  pills.forEach((p, i) => setTimeout(() => p.classList.add('visible'), i * 120));
}

async function playSegment2(root: HTMLElement): Promise<void> {
  const stream = root.querySelector<HTMLElement>('[data-commit-stream]');
  const cards = root.querySelectorAll<HTMLElement>('[data-decision-card]');
  if (!stream) return;

  if (reduced()) {
    COMMITS.forEach((c) => appendCommit(stream, c));
    cards.forEach((card) => card.classList.add('visible'));
    return;
  }

  let cardIndex = 0;
  for (const c of COMMITS) {
    appendCommit(stream, c);
    stream.scrollTop = stream.scrollHeight;
    if (c.hit && cards[cardIndex]) {
      cards[cardIndex].classList.add('visible');
      cardIndex++;
    }
    await sleep(440);
  }
}

function appendCommit(stream: HTMLElement, c: { sha: string; msg: string; hit: boolean }): void {
  const row = document.createElement('div');
  row.className = `flex items-center gap-2.5 py-1.5 text-[12px] ${
    c.hit ? 'rounded-md bg-accent/10 -mx-2 px-2' : ''
  }`;
  row.innerHTML =
    `<span class="h-2 w-2 rounded-full flex-none ${c.hit ? 'bg-accent' : 'bg-muted'}"></span>` +
    `<span class="text-muted flex-none">${c.sha}</span>` +
    `<span class="${c.hit ? 'text-primary' : 'text-secondary'} truncate">${c.msg}</span>` +
    (c.hit ? `<span class="ml-auto flex-none text-accent text-[10px]">● captured</span>` : '');
  stream.appendChild(row);
}

async function playSegment3(root: HTMLElement): Promise<void> {
  const stream = root.querySelector<HTMLElement>('[data-asm-stream]');
  const badge = root.querySelector<HTMLElement>('[data-asm-badge]');
  const response = root.querySelector<HTMLElement>('[data-asm-response]');
  if (!stream) return;

  const renderStep = (label: string, done: string) => {
    const row = document.createElement('div');
    row.className = 'flex items-center justify-between text-[12px] text-secondary';
    row.innerHTML = `<span>${label}</span><span class="text-green">${done}</span>`;
    stream.appendChild(row);
    return row;
  };

  if (reduced()) {
    ASM_STEPS.forEach((s) => renderStep(s.label.replace('⟳', '✓'), s.done));
    badge?.classList.add('on');
    response?.classList.add('on');
    return;
  }

  for (const step of ASM_STEPS) {
    const row = renderStep(step.label, '');
    await sleep(260);
    const right = row.querySelector('span:last-child');
    if (right) right.textContent = step.done;
    const left = row.querySelector('span:first-child');
    if (left) left.textContent = step.label.replace('⟳', '✓');
  }
  const ranking = document.createElement('div');
  ranking.className = 'mt-1 text-[12px] text-muted';
  ranking.textContent = 'ranking + deduplicating · assembling 3,240 tokens...';
  stream.appendChild(ranking);
  await sleep(500);
  badge?.classList.add('on');
  await sleep(300);
  response?.classList.add('on');
}

export function initStickyScroll(): void {
  if (typeof document === 'undefined') return;
  const root = document.querySelector<HTMLElement>('[data-product]');
  if (!root) return;

  const segments = Array.from(root.querySelectorAll<HTMLElement>('[data-segment]'));
  const played = new Set<string>();

  const players: Record<string, (r: HTMLElement) => Promise<void>> = {
    '1': playSegment1,
    '2': playSegment2,
    '3': playSegment3,
  };

  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const idx = (entry.target as HTMLElement).dataset.segment!;
          setActiveStage(root, Number(idx));
          if (!played.has(idx)) {
            played.add(idx);
            void players[idx]?.(root);
          }
        }
      },
      { threshold: 0.5, rootMargin: '0px 0px -10% 0px' },
    );
    segments.forEach((s) => io.observe(s));
  } else {
    segments.forEach((s) => {
      const idx = s.dataset.segment!;
      played.add(idx);
      void players[idx]?.(root);
    });
  }

  // Mobile tab interface
  const tabs = Array.from(root.querySelectorAll<HTMLElement>('[data-product-tab]'));
  if (tabs.length) {
    tabs.forEach((tab) => {
      tab.addEventListener('click', () => {
        const idx = tab.dataset.productTab!;
        tabs.forEach((t) =>
          t.classList.toggle('tab-active', t.dataset.productTab === idx),
        );
        segments.forEach((s) =>
          s.classList.toggle('mobile-hidden', s.dataset.segment !== idx),
        );
        setActiveStage(root, Number(idx));
        if (!played.has(idx)) {
          played.add(idx);
          void players[idx]?.(root);
        }
      });
    });
  }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStickyScroll, { once: true });
  } else {
    initStickyScroll();
  }
}
