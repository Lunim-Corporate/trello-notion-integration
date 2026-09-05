import requests

from config import TRELLO_API_KEY, TRELLO_BOARD_ID, TRELLO_TOKEN

BASE_URL = "https://api.trello.com/1"


def _auth_params(extra=None):
    params = {"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
    if extra:
        params.update(extra)
    return params


def get_lists() -> dict:
    """Returns {list_name: list_id} for the configured board."""
    resp = requests.get(f"{BASE_URL}/boards/{TRELLO_BOARD_ID}/lists", params=_auth_params())
    resp.raise_for_status()
    return {lst["name"]: lst["id"] for lst in resp.json()}


def get_labels() -> dict:
    """Returns {label_name: label_id} for the configured board."""
    resp = requests.get(
        f"{BASE_URL}/boards/{TRELLO_BOARD_ID}/labels",
        params=_auth_params({"limit": 1000}),
    )
    resp.raise_for_status()
    return {lbl["name"]: lbl["id"] for lbl in resp.json() if lbl["name"]}


def get_card(card_id: str) -> dict:
    resp = requests.get(
        f"{BASE_URL}/cards/{card_id}",
        params=_auth_params({"fields": "name,desc,due,idList,idLabels,idMembers,shortUrl"}),
    )
    resp.raise_for_status()
    return resp.json()


def update_card(card_id: str, *, name=None, desc=None, due=None, id_list=None, id_labels=None):
    payload = {}
    if name is not None:
        payload["name"] = name
    if desc is not None:
        payload["desc"] = desc
    if due is not None:
        payload["due"] = due
    if id_list is not None:
        payload["idList"] = id_list
    if id_labels is not None:
        payload["idLabels"] = ",".join(id_labels)

    resp = requests.put(f"{BASE_URL}/cards/{card_id}", params=_auth_params(payload))
    resp.raise_for_status()
    return resp.json()


def register_webhook(callback_url: str, description: str = "Notion sync") -> dict:
    resp = requests.post(
        f"{BASE_URL}/webhooks",
        params=_auth_params(
            {
                "callbackURL": callback_url,
                "idModel": TRELLO_BOARD_ID,
                "description": description,
            }
        ),
    )
    resp.raise_for_status()
    return resp.json()
