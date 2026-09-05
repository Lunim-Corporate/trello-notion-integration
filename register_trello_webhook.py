"""
Run this once, after deploying the app, to register the Trello webhook.

Usage:
    python register_trello_webhook.py https://your-deployed-app.com/trello-webhook
"""
import sys

import trello_client

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python register_trello_webhook.py <callback_url>")
        sys.exit(1)

    callback_url = sys.argv[1]
    result = trello_client.register_webhook(callback_url)
    print("Registered webhook:", result)
