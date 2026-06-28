# Screenshots

This directory contains screenshots and demo assets used in the README and documentation.

## Assets

- `screenshot-cli.png` - `dot status` output showing daemon, indexed files, chunks, memories, and top contexts.
- `screenshot-dashboard.png` - The Dot web dashboard with stats, search, and ranked matches.
- `screenshot-extension.png` - The Dot sidebar in VS Code showing decisions and related code.
- `demo.gif` - Animated walkthrough of the core workflow: `dot init`, `dot daemon start`, `dot ask`, and the ranked results.

## Regenerating assets

The PNG and GIF assets are generated with Pillow from `scripts/generate_assets.py` so they stay consistent with the Field Notes theme.

```bash
python3 scripts/generate_assets.py
```

To capture real screenshots instead, use your OS screenshot tool while Dot is running and save them here with the same filenames.
