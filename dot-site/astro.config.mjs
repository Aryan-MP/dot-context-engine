import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';

// https://astro.build
export default defineConfig({
  integrations: [tailwind()],
  output: 'static',
  site: 'https://dotmemory.dev',
  compressHTML: true,
});
