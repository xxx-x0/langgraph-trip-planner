"""Classify observed ticket results without guessing from localized messages."""


def ticket_outcome(result):
    if result['recommendations']:
        return 'fallback' if result.get('ranked_by') == 'rules' else 'recommended'
    reason = result.get('empty_reason')
    if reason is None:
        preferences = bool(result.get('preference_excluded'))
        schedule = bool(result.get('excluded'))
        reason = 'mixed' if preferences and schedule else 'preferences' if preferences else 'schedule' if schedule else 'availability'
    return {'preferences':'empty_preferences', 'schedule':'empty_conflict',
            'mixed':'empty_mixed_constraints', 'availability':'empty_unavailable'}[reason]
