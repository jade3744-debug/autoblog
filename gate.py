"""Content-integrity gate. Approval authentication belongs to an external service."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

SCORES = ('intent', 'accuracy', 'originality', 'readability', 'images')

def digest(directory):
    base = Path(directory)
    if not base.is_dir() or base.is_symlink():
        raise ValueError('BUNDLE_DIRECTORY_REQUIRED')
    records = []
    for path in sorted(base.rglob('*')):
        if path.is_symlink():
            raise ValueError('SYMLINK_NOT_ALLOWED')
        if path.is_file():
            records.append([path.relative_to(base).as_posix(),
                            hashlib.sha256(path.read_bytes()).hexdigest()])
    if not records:
        raise ValueError('EMPTY_BUNDLE')
    return hashlib.sha256(json.dumps(records, ensure_ascii=False,
                         separators=(',', ':')).encode()).hexdigest()

def check_review(directory, review):
    current = digest(directory)
    if review.get('artifact_sha256') != current:
        raise ValueError('REVIEW_CONTENT_CHANGED')
    if review.get('model') != 'gpt-6.1-sol' or review.get('reasoning') != 'medium':
        raise ValueError('REVIEW_MODEL_MISMATCH')
    if review.get('verdict') != 'PASS' or review.get('blockers') != []:
        raise ValueError('QUALITY_HOLD')
    scores = review.get('scores', {})
    if not isinstance(scores, dict) or set(scores) != set(SCORES):
        raise ValueError('INVALID_SCORE_FIELDS')
    values = list(scores.values())
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 100
           for v in values):
        raise ValueError('INVALID_SCORE_VALUE')
    if min(values) < 80 or sum(values) / len(values) < 85:
        raise ValueError('QUALITY_SCORE_TOO_LOW')
    return current

def check_publish(directory, review, approval):
    current = check_review(directory, review)
    if approval.get('approved') is not True:
        raise ValueError('USER_APPROVAL_REQUIRED')
    if approval.get('artifact_sha256') != current:
        raise ValueError('APPROVAL_CONTENT_CHANGED')
    if not isinstance(approval.get('approved_by'), str) or not approval['approved_by'].strip():
        raise ValueError('APPROVER_REQUIRED')
    try:
        when = datetime.fromisoformat(approval['approved_at'].replace('Z', '+00:00'))
        if when.tzinfo is None or when > datetime.now(timezone.utc):
            raise ValueError()
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('INVALID_APPROVAL_TIME') from None
    return current

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('digest', 'check-review', 'check-publish'))
    parser.add_argument('bundle', type=Path)
    parser.add_argument('review', type=Path, nargs='?')
    parser.add_argument('approval', type=Path, nargs='?')
    args = parser.parse_args()
    try:
        if args.command == 'digest':
            result = digest(args.bundle)
        else:
            if args.review is None:
                raise ValueError('REVIEW_REQUIRED')
            if args.review.resolve().is_relative_to(args.bundle.resolve()):
                raise ValueError('REVIEW_MUST_BE_OUTSIDE_BUNDLE')
            review = json.loads(args.review.read_text(encoding='utf-8'))
            if not isinstance(review, dict):
                raise ValueError('INVALID_REVIEW')
            if args.command == 'check-review':
                result = check_review(args.bundle, review)
            else:
                if args.approval is None:
                    raise ValueError('APPROVAL_REQUIRED')
                if args.approval.resolve().is_relative_to(args.bundle.resolve()):
                    raise ValueError('APPROVAL_MUST_BE_OUTSIDE_BUNDLE')
                approval = json.loads(args.approval.read_text(encoding='utf-8'))
                if not isinstance(approval, dict):
                    raise ValueError('INVALID_APPROVAL')
                result = check_publish(args.bundle, review, approval)
        print(json.dumps({'status': 'OK', 'artifact_sha256': result}))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error)}))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
