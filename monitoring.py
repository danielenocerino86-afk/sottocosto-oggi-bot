"""Persist run outcomes and notify an optional heartbeat service without logging URLs."""
import os
import requests


def run_monitored(action, store):
    run = store.start_run()
    status = 'error'
    try:
        action()
        status = 'ok'
    finally:
        store.end_run(run, status)
        endpoint = os.environ.get('HEALTHCHECK_URL')
        if endpoint:
            try:
                requests.get(endpoint + ('' if status == 'ok' else '/fail'), timeout=10).raise_for_status()
            except requests.RequestException:
                print('[MONITOR] Heartbeat delivery failed', flush=True)
