"""Explainable 0..100 ranking; historic lows mean observed lows, not market lows."""
import math
from storage import cents


def score_deal(deal, previous_min=None):
    current = cents(deal['current_price']) / 100
    original = cents(deal['original_price']) / 100
    if original <= current:
        raise ValueError('No verified discount')
    discount = min(70, (original - current) / original * 100)
    rating = float(deal.get('rating') or 0)
    reviews = max(0, int(deal.get('review_count') or 0))
    if not math.isfinite(rating) or not 0 <= rating <= 5:
        raise ValueError('Invalid rating')
    parts = {'discount': round(discount / 70 * 50, 2),
             'rating': round(rating / 5 * 20 * min(1, reviews / 100), 2),
             'reviews': round(min(1, math.log10(reviews + 1) / 4) * 10, 2),
             'observed_low': 10 if previous_min and current <= previous_min else 0,
             'active_deal': 10 if deal.get('has_deal') else 0}
    return round(sum(parts.values()), 2), parts


def rank_diverse(deals, category):
    groups = {}
    for deal in sorted(deals, key=lambda d: (-d['score'], d['asin'])):
        groups.setdefault(category(deal['title']), []).append(deal)
    result = []
    while groups:
        for key in sorted(groups, key=lambda k: -groups[k][0]['score']):
            result.append(groups[key].pop(0))
        groups = {k: v for k, v in groups.items() if v}
    return result
