/**
 * Scroll-triggered reveal. Adds `.visible` to `.reveal` elements once they
 * cross into view, then unobserves them. Uses a single shared observer.
 * Safe to call multiple times (idempotent per element).
 */

const REVEALED = new WeakSet<Element>();

export function initReveal(): void {
  if (typeof window === 'undefined') return;

  const elements = Array.from(document.querySelectorAll<HTMLElement>('.reveal')).filter(
    (el) => !REVEALED.has(el),
  );
  if (elements.length === 0) return;

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReduced || !('IntersectionObserver' in window)) {
    elements.forEach((el) => {
      el.classList.add('visible');
      REVEALED.add(el);
    });
    return;
  }

  const observer = new IntersectionObserver(
    (entries, obs) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          REVEALED.add(entry.target);
          obs.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.2, rootMargin: '0px 0px -50px 0px' },
  );

  elements.forEach((el) => {
    REVEALED.add(el);
    observer.observe(el);
  });
}

/**
 * Run a callback once when an element first enters the viewport.
 * Returns a disconnect function.
 */
export function onceInView(
  el: Element,
  cb: () => void,
  options: IntersectionObserverInit = { threshold: 0.35 },
): () => void {
  if (typeof window === 'undefined' || !('IntersectionObserver' in window)) {
    cb();
    return () => {};
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        cb();
        observer.disconnect();
      }
    }
  }, options);
  observer.observe(el);
  return () => observer.disconnect();
}

// Auto-init when imported directly in a page context.
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initReveal, { once: true });
  } else {
    initReveal();
  }
}
