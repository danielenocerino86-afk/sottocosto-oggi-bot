"""Offline state operations. Run with the same DATABASE_URL as the workers."""
import argparse
import datetime as dt
import json
from pathlib import Path
from storage import Store, cents
from zoneinfo import ZoneInfo


def import_legacy(store, path):
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError('Invalid legacy history')
    with store.tx() as db:
        db.execute("INSERT INTO metadata VALUES ('legacy-import','pending') ON CONFLICT(key) DO NOTHING")
        row = db.execute("SELECT value FROM metadata WHERE key='legacy-import'" + (' FOR UPDATE' if store.pg else '')).fetchone()
        if row[0] == 'complete':
            return
        for day, entries in data.items():
            date = dt.date.fromisoformat(day)
            ts = dt.datetime.combine(date, dt.time(), ZoneInfo('Europe/Rome')).timestamp()
            for key in entries:
                info = entries[key] if isinstance(entries, dict) else {}
                price = info.get('price') if isinstance(info, dict) else None
                dbkey = key + ':' + day if key.startswith('_') else key
                payload = {'asin': key, 'title': 'Pubblicazione importata', 'current_price': price} if not key.startswith('_') else {}
                db.execute('INSERT INTO publications VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(token) DO NOTHING', ('legacy:' + day + ':' + key, dbkey, cents(price) if price is not None else None, ts, day, json.dumps(payload)))
        db.execute("UPDATE metadata SET value='complete' WHERE key='legacy-import'")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('import').add_argument('file')
    resolve = sub.add_parser('resolve')
    resolve.add_argument('key')
    resolve.add_argument('--outcome', choices=['sent', 'not-sent'], required=True)
    resolve.add_argument('--price')
    args = parser.parse_args()
    store = Store()
    if args.command == 'status':
        print(json.dumps(store.status(), indent=2))
    elif args.command == 'import':
        import_legacy(store, args.file)
    else:
        deal = None
        if args.outcome == 'sent' and not args.key.startswith('_'):
            if not args.price:
                parser.error('--price required for confirmed product delivery')
            deal = {'asin': args.key, 'current_price': cents(args.price) / 100, 'title': 'Invio riconciliato'}
        store.resolve(args.key, args.outcome == 'sent', deal)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('State operation failed; no credentials logged') from None
