# Nextdoor Scanner

Automated Nextdoor scanner for Bulqit service opportunities in the San Fernando Valley area of Los Angeles.

## Features

- **Dual 2FA Support**:
  - Manual 2FA for local testing
  - Automated GitHub Gist 2FA for GitHub Actions
- **Service Detection**: Scans for pool cleaning, window washing, lawn care, pest control, etc.
- **AI Analysis**: Uses Groq AI to filter relevant business opportunities
- **Email Reports**: Sends clean HTML emails with JSON attachments
- **Anti-Detection**: Human-like scrolling and typing patterns

## Files

- `nextdoor_complete.py` - Main consolidated scanner with all dependencies
- `keys.txt` - Groq API key(s) for AI analysis

## Environment Variables

For local testing:
- None required (uses manual 2FA)

For GitHub Actions:
- `GIST_TOKEN` - GitHub personal access token for Gist creation
- `GITHUB_ACTIONS=true` - Automatically set by GitHub Actions

## Usage

```bash
python3 nextdoor_complete.py
```

The scanner will automatically detect if it's running locally or in GitHub Actions and use the appropriate 2FA method.