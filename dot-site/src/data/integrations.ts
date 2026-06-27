export type IntegrationStatus = 'available' | 'coming-soon';

export interface Integration {
  name: string;
  method: string;
  description: string;
  status: IntegrationStatus;
  icon: string;
}

export const integrations: Integration[] = [
  {
    name: 'Claude Code',
    method: 'MCP Server',
    description: 'Native tool calls. Zero config. dot init and done.',
    status: 'available',
    icon: 'claude',
  },
  {
    name: 'GitHub Copilot',
    method: 'VS Code API',
    description: 'Context injected automatically on every file switch.',
    status: 'available',
    icon: 'github',
  },
  {
    name: 'Cursor',
    method: 'REST API',
    description: 'Rules injection plus real-time context endpoint.',
    status: 'available',
    icon: 'cursor',
  },
  {
    name: 'Neovim',
    method: 'Lua plugin',
    description: 'For the terminal purists. Full feature parity.',
    status: 'available',
    icon: 'neovim',
  },
  {
    name: 'Ollama',
    method: 'Direct',
    description: '100% offline. No APIs. No data ever leaves.',
    status: 'coming-soon',
    icon: 'ollama',
  },
  {
    name: 'JetBrains',
    method: 'Plugin',
    description: 'IntelliJ, PyCharm, WebStorm, GoLand.',
    status: 'coming-soon',
    icon: 'jetbrains',
  },
  {
    name: 'Continue.dev',
    method: 'REST API',
    description: 'Open source IDE extension gets full memory.',
    status: 'coming-soon',
    icon: 'continue',
  },
  {
    name: 'Zed',
    method: 'Extension',
    description: 'The fast editor gets a long memory.',
    status: 'coming-soon',
    icon: 'zed',
  },
];
