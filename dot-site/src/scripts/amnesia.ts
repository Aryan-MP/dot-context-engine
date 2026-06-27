/**
 * The amnesia terminal animation.
 *
 * State machine: WITHOUT_DOT → RESET → TRANSITION → WITH_DOT → (loop).
 * A developer keeps re-explaining their stack to a forgetful AI; Dot connects
 * and the next session already knows everything. Honors reduced-motion by
 * rendering a static "with dot" end-state.
 */

type Role = 'you' | 'ai' | 'ai-cont' | 'sys-accent' | 'sys-green' | 'muted' | 'secondary';

interface SayOpts {
  typed?: boolean;
  pause?: number;
  fade?: boolean;
  speed?: number;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const reduced = () =>
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const ROLE_LABEL: Partial<Record<Role, string>> = { you: 'you', ai: 'ai' };
const ROLE_LABEL_CLASS: Partial<Record<Role, string>> = {
  you: 'text-green',
  ai: 'text-accent',
};
const ROLE_TEXT_CLASS: Record<Role, string> = {
  you: 'text-primary',
  ai: 'text-primary',
  'ai-cont': 'text-primary',
  'sys-accent': 'text-accent',
  'sys-green': 'text-green',
  muted: 'text-muted',
  secondary: 'text-secondary',
};

class AmnesiaTerminal {
  private root: HTMLElement;
  private body: HTMLElement;
  private title: HTMLElement | null;
  private flash: HTMLElement | null;
  private pulse: HTMLElement | null;
  private recount: HTMLElement | null;
  private extCount: HTMLElement | null;
  private extCountWrap: HTMLElement | null;
  private running = false;

  constructor(root: HTMLElement) {
    this.root = root;
    this.body = root.querySelector<HTMLElement>('[data-amnesia-body]')!;
    this.title = root.querySelector<HTMLElement>('[data-amnesia-title]');
    this.flash = root.querySelector<HTMLElement>('.flash-overlay');
    this.pulse = root.querySelector<HTMLElement>('.pulse-ring');
    this.recount = root.querySelector<HTMLElement>('[data-amnesia-recount]');
    this.extCount = document.querySelector<HTMLElement>('[data-amnesia-count]');
    this.extCountWrap = document.querySelector<HTMLElement>('[data-amnesia-counter]');
  }

  private alive(): boolean {
    return document.body.contains(this.root);
  }

  private clear(): void {
    this.body.innerHTML = '';
  }

  private setTitle(text: string): void {
    if (this.title) this.title.textContent = text;
  }

  private setGlow(on: boolean): void {
    this.root.classList.toggle('with-dot', on);
  }

  private setCounter(n: number, good = false): void {
    if (this.recount) {
      this.recount.textContent = `re-explained: ${n}`;
      this.recount.classList.toggle('text-green', good);
      this.recount.classList.toggle('text-red', !good && n > 0);
      this.recount.classList.toggle('text-muted', n === 0 && !good);
    }
    if (this.extCount) this.extCount.textContent = String(n);
    if (this.extCountWrap) {
      this.extCountWrap.classList.toggle('text-green', good);
      this.extCountWrap.classList.toggle('text-red', !good && n > 0);
    }
  }

  private newLine(role: Role): { line: HTMLElement; textSpan: HTMLElement } {
    const line = document.createElement('div');
    line.className = `flex gap-2 items-start ${role === 'ai-cont' ? 'pl-[2.6rem]' : ''}`;

    const label = ROLE_LABEL[role];
    if (label) {
      const labelEl = document.createElement('span');
      labelEl.className = `flex-none w-8 ${ROLE_LABEL_CLASS[role] ?? ''}`;
      labelEl.textContent = `${label}:`;
      line.appendChild(labelEl);
    }

    const textSpan = document.createElement('span');
    textSpan.className = `${ROLE_TEXT_CLASS[role]} min-w-0`;
    line.appendChild(textSpan);

    this.body.appendChild(line);
    this.scrollDown();
    return { line, textSpan };
  }

  private scrollDown(): void {
    this.body.scrollTop = this.body.scrollHeight;
  }

  private async type(target: HTMLElement, text: string, speed: number): Promise<void> {
    const caret = document.createElement('span');
    caret.className = 'caret';
    const content = document.createElement('span');
    target.appendChild(content);
    target.appendChild(caret);
    for (let i = 0; i < text.length; i++) {
      content.textContent += text[i];
      this.scrollDown();
      await sleep(speed);
    }
    caret.remove();
  }

  private async say(role: Role, text: string, opts: SayOpts = {}): Promise<void> {
    const { textSpan, line } = this.newLine(role);
    const speed = opts.speed ?? (role === 'you' ? 26 : 13);
    if (opts.typed !== false && !reduced()) {
      await this.type(textSpan, text, speed);
    } else {
      textSpan.textContent = text;
    }
    if (opts.fade) {
      line.style.transition = 'opacity 700ms var(--easing), filter 700ms var(--easing)';
      await sleep(250);
      line.style.opacity = '0.4';
    }
    await sleep(opts.pause ?? 350);
  }

  private code(lines: string[]): void {
    const block = document.createElement('div');
    block.className =
      'my-1 ml-[2.6rem] rounded-md border border-border bg-bg/70 px-3 py-2 text-[12px] leading-relaxed text-muted';
    for (const l of lines) {
      const row = document.createElement('div');
      row.textContent = l;
      block.appendChild(row);
    }
    this.body.appendChild(block);
    this.scrollDown();
  }

  private async thinking(ms: number): Promise<void> {
    const { textSpan } = this.newLine('ai');
    textSpan.innerHTML =
      '<span class="thinking" aria-label="thinking"><span></span><span></span><span></span></span>';
    this.scrollDown();
    await sleep(ms);
    textSpan.closest('div')?.remove();
  }

  private async doFlash(): Promise<void> {
    if (!this.flash) return;
    this.flash.classList.remove('go');
    void this.flash.offsetWidth; // reflow to restart animation
    this.flash.classList.add('go');
    await sleep(500);
  }

  private async doPulse(): Promise<void> {
    if (!this.pulse) return;
    this.pulse.classList.remove('go');
    void this.pulse.offsetWidth;
    this.pulse.classList.add('go');
    await sleep(1000);
  }

  private async blurClear(): Promise<void> {
    this.body.style.transition = 'filter 500ms var(--easing), opacity 500ms var(--easing)';
    this.body.style.filter = 'blur(4px)';
    this.body.style.opacity = '0';
    await sleep(500);
    this.clear();
    this.body.style.filter = '';
    this.body.style.opacity = '1';
  }

  // ---- phases ----

  private async withoutDot(): Promise<void> {
    this.setGlow(false);
    this.setTitle('ai-session');
    this.setCounter(2);
    this.clear();

    await this.say('muted', '~/my-project', { typed: false, pause: 200 });
    await this.say('secondary', '> new ai session', { typed: false, pause: 400 });
    await this.say('muted', ' ', { typed: false, pause: 100 });

    await this.say('you', 'help me add rate limiting to auth service', { pause: 800 });
    await this.say('ai', "sure! what's your tech stack?", { pause: 600 });
    await this.say('you', 'node.js, express, redis for caching', { pause: 800 });
    await this.say('ai', "got it. here's how to implement it...", { pause: 150 });
    this.code([
      '// express-rate-limit with redis store',
      'const limiter = rateLimit({ windowMs: 60000, max: 100 })',
    ]);
    await sleep(600);
    await this.say('you', 'perfect. now add it to payments endpoint too', { pause: 800 });
    await this.say('ai', "of course! what's your—", { pause: 700 });
  }

  private async reset(): Promise<void> {
    await this.blurClear();
    await this.doFlash();
    this.setCounter(3);
    this.setTitle('ai-session · context lost');
    await sleep(250);

    await this.say('ai', 'hello! how can i help you today?', { pause: 500 });
    await this.say('you', 'ugh. we’re using node.js, express...', {
      speed: 40,
      pause: 600,
      fade: true,
    });
    await sleep(500);
  }

  private async transition(): Promise<void> {
    await this.doPulse();
    await this.say('sys-accent', '●  dot daemon connected', { typed: false, pause: 250 });
    await this.say('sys-green', '✓  context loaded · 3,847 files · 23 decisions', {
      typed: false,
      pause: 700,
    });
  }

  private async withDot(): Promise<void> {
    this.setGlow(true);
    this.setTitle('ai-session · ● dot connected');
    this.clear();

    await this.say('muted', ' ', { typed: false, pause: 150 });
    await this.say('you', 'add rate limiting to payments endpoint', { pause: 200 });
    await this.thinking(1200);
    await this.say('ai', "on it. i can see you're using express-rate-limit", { pause: 120 });
    await this.say('ai-cont', 'on auth (added tuesday). applying same pattern', {
      pause: 120,
    });
    await this.say('ai-cont', 'to payments with a tighter limit given the SLA.', {
      pause: 150,
    });
    this.code([
      'const paymentsLimiter = rateLimit({',
      '  windowMs: 60000,',
      '  max: 20,  // tighter — payments SLA',
      '  store: redisStore  // same redis instance',
      '})',
    ]);
    await sleep(600);
    await this.say('you', 'exactly what i needed', { pause: 600 });
    await this.say('ai', '✓ consistent with your auth pattern', { pause: 300 });
    this.setCounter(0, true);
    await sleep(2000);
  }

  private renderStatic(): void {
    this.setGlow(true);
    this.setTitle('ai-session · ● dot connected');
    this.setCounter(0, true);
    this.clear();
    const seq: Array<[Role, string]> = [
      ['you', 'add rate limiting to payments endpoint'],
      ['ai', "on it. i can see you're using express-rate-limit on auth"],
      ['ai-cont', '(added tuesday). applying the same pattern to payments'],
      ['ai-cont', 'with a tighter limit given the SLA.'],
    ];
    for (const [role, text] of seq) {
      const { textSpan } = this.newLine(role);
      textSpan.textContent = text;
    }
    this.code([
      'const paymentsLimiter = rateLimit({',
      '  windowMs: 60000, max: 20,  // tighter — payments SLA',
      '  store: redisStore  // same redis instance',
      '})',
    ]);
    const { textSpan } = this.newLine('ai');
    textSpan.textContent = '✓ consistent with your auth pattern';
  }

  async start(): Promise<void> {
    if (this.running) return;
    this.running = true;

    if (reduced()) {
      this.renderStatic();
      return;
    }

    while (this.alive()) {
      await this.withoutDot();
      if (!this.alive()) break;
      await this.reset();
      if (!this.alive()) break;
      await this.transition();
      if (!this.alive()) break;
      await this.withDot();
    }
  }
}

export function initAmnesiaTerminal(root: HTMLElement): void {
  const term = new AmnesiaTerminal(root);
  // Defer start until the hero is actually visible to save cycles.
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          void term.start();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(root);
  } else {
    void term.start();
  }
}

export function initAmnesia(): void {
  if (typeof document === 'undefined') return;
  const root = document.querySelector<HTMLElement>('[data-amnesia]');
  if (root) initAmnesiaTerminal(root);
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAmnesia, { once: true });
  } else {
    initAmnesia();
  }
}
