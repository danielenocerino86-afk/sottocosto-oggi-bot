"""One committed claim per product; no retry after an ambiguous Telegram response."""
import requests


class UnknownDelivery(RuntimeError):
    pass


def send(token, channel, text, image_url=None, reply_markup=None):
    method = 'sendPhoto' if image_url else 'sendMessage'
    payload = {'chat_id': channel, 'parse_mode': 'HTML'}
    payload.update({'photo': image_url, 'caption': text} if image_url else {'text': text, 'disable_web_page_preview': True})
    if reply_markup:
        payload['reply_markup'] = reply_markup
    try:
        response = requests.post(f'https://api.telegram.org/bot{token}/{method}', json=payload, timeout=(5, 25))
        data = response.json()
        if response.status_code == 200 and data.get('ok') is True:
            return True
        if 400 <= response.status_code < 500 and data.get('ok') is False:
            return False
    except (requests.RequestException, ValueError):
        pass
    # Do not include exception text: requests errors may embed the credential URL.
    raise UnknownDelivery('Telegram delivery requires reconciliation')


def publish(store, deal, sender):
    key = deal['asin']
    claim = store.claim(key, deal['current_price'])
    if not claim:
        return False
    try:
        ok = sender()
    except Exception:
        store.finish(key, claim, 'unknown')
        raise UnknownDelivery('Telegram delivery requires reconciliation') from None
    store.finish(key, claim, 'sent' if ok else 'rejected', deal)
    return ok
