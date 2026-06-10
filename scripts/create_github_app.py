#!/usr/bin/env python3
"""Helper: print instructions for registering the GitHub App."""
import sys


def main() -> None:
    print("""
== GitHub App Registration ==

1. Go to: https://github.com/settings/apps/new
2. Fill in:
   - App name: gitprbot (or your choice)
   - Homepage URL: https://github.com/ilovehhhyn/gitprbot
   - Webhook URL: https://<your-orchestrator-host>/webhooks/github
   - Webhook secret: (generate a random string, save to GITHUB_WEBHOOK_SECRET in .env)

3. Permissions (Repository):
   - Contents: Read & write
   - Pull requests: Read & write
   - Issues: Read & write
   - Metadata: Read-only

4. Subscribe to events:
   - Pull request
   - Issue comment
   - Pull request review comment
   - Issues

5. After creating the app:
   - Note the App ID -> set GITHUB_APP_ID in .env
   - Generate a private key -> download and set GITHUB_APP_PRIVATE_KEY_PATH in .env
   - Install the app on target repos -> note the installation ID

6. To find installation IDs:
   curl -H "Authorization: Bearer <app-jwt>" https://api.github.com/app/installations
""")


if __name__ == "__main__":
    main()
