# Uploading the GitHub social preview

GitHub shows a social preview card when the repo is shared on Twitter, LinkedIn, Slack, etc.

## Asset

The preview image is already generated:

```
branding/social-preview.png
```

## Steps

1. Go to https://github.com/Aryan-MP/dot-context-engine/settings
2. Scroll down to **Social preview**
3. Click **Edit**
4. Upload `branding/social-preview.png`
5. Click **Save changes**

## Regenerating

If the design/theme changes, regenerate the PNG from the SVG source:

```bash
python3 scripts/generate_assets.py
```

Or open `branding/social-preview.svg` in a browser/design tool and export to PNG (1280x640 px).
