/**
 * Inline SVG inner-markup for tool + UI icons.
 * Each value is the *inner* content of an SVG with viewBox="0 0 24 24"
 * (github/claude use their own coords noted inline). Rendered by passing
 * `set:html` into a wrapping <svg>. Keeps the bundle image-free and the
 * build dependency-free (no iconify network fetch).
 */
export const icons: Record<string, string> = {
  // Tools
  claude:
    '<path d="M12 3l2.4 6.3L21 12l-6.6 2.7L12 21l-2.4-6.3L3 12l6.6-2.7z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>',
  github:
    '<g transform="scale(1.5)"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.42 7.42 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></g>',
  cursor:
    '<path d="M12 2l9 5.5v9L12 22l-9-5.5v-9L12 2zm0 0v20M3 7.5l18 9M21 7.5l-18 9" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  neovim:
    '<path d="M5 4l5 6-5 10V4zM19 20l-5-6 5-10v16z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  ollama:
    '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="12" cy="12" r="3.3" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  jetbrains:
    '<rect x="3" y="3" width="18" height="18" rx="3" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7.5 16.5h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M8 7.5v5.5a2 2 0 0 0 2 2" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  continue:
    '<path d="M5 12h13M12 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
  zed:
    '<path d="M5 5h14L5 19h14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',

  // Inputs / UI
  file:
    '<path d="M14 3v5h5M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-5z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 13h8M8 17h5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
  git:
    '<circle cx="6" cy="6" r="2.4" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="6" cy="18" r="2.4" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="18" cy="9" r="2.4" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M6 8.4v7.2M8.2 7.2A6 6 0 0 1 15.6 9.4" fill="none" stroke="currentColor" stroke-width="1.5"/>',
  chat:
    '<path d="M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 4v-4H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  brain:
    '<path d="M9 4a2.5 2.5 0 0 0-2.5 2.5A2.5 2.5 0 0 0 5 11a2.5 2.5 0 0 0 1.5 4A2.5 2.5 0 0 0 9 20a1.5 1.5 0 0 0 1.5-1.5V5.5A1.5 1.5 0 0 0 9 4zM15 4a2.5 2.5 0 0 1 2.5 2.5A2.5 2.5 0 0 1 19 11a2.5 2.5 0 0 1-1.5 4A2.5 2.5 0 0 1 15 20a1.5 1.5 0 0 1-1.5-1.5V5.5A1.5 1.5 0 0 1 15 4z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
  terminal:
    '<rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 9l3 3-3 3M13 15h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
  star:
    '<path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.6L12 18.5 6.1 21.6l1.2-6.6L2.5 9.4l6.6-.9z" fill="currentColor"/>',
  arrowRight:
    '<path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  chevronDown:
    '<path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  menu:
    '<path d="M4 7h16M4 12h16M4 17h16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  close:
    '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  pin:
    '<path d="M12 2a6 6 0 0 0-6 6c0 4 6 12 6 12s6-8 6-12a6 6 0 0 0-6-6z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><circle cx="12" cy="8" r="2" fill="currentColor"/>',
  check:
    '<path d="M5 12.5l4.5 4.5L19 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  apple:
    '<path d="M16 13c0-3 2.4-3.6 2.5-3.7-1.4-2-3.5-2.3-4.3-2.3-1.8-.2-3.5 1-4.4 1-.9 0-2.3-1-3.8-1C4 7 2 8.7 2 12c0 3.3 2.4 7 4 7 1 0 1.7-.7 3-.7s1.9.7 3 .7c1.7 0 3.3-3.2 3.5-4.3-1.9-.7-2.5-2.4-2.5-2.4z" fill="currentColor"/><path d="M13.5 5.5c.8-1 1.3-2.3 1.1-3.5-1.1.1-2.4.8-3.1 1.7-.7.8-1.3 2.1-1.1 3.3 1.2.1 2.4-.6 3.1-1.5z" fill="currentColor"/>',
  linux:
    '<path d="M9 3.5c-1 .8-1 2.6-1 4 0 1.2-.6 2-1.3 3-1 1.4-2.2 3-2.2 5 0 1.5 1 2.5 2 3 .5 1.3 2.4 2 5.5 2s5-.7 5.5-2c1-.5 2-1.5 2-3 0-2-1.2-3.6-2.2-5-.7-1-1.3-1.8-1.3-3 0-1.4 0-3.2-1-4-.7-.6-1.7-1-3-1s-2.3.4-3 1z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="10" cy="9" r=".9" fill="currentColor"/><circle cx="14" cy="9" r=".9" fill="currentColor"/>',
  windows:
    '<path d="M3 5.5l7.5-1v7H3v-6zM11.5 4.3L21 3v8.5h-9.5v-7.2zM3 13.5h7.5v6L3 18.5v-5zM11.5 13.5H21V21l-9.5-1.3v-6.2z" fill="currentColor"/>',
};
