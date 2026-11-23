"""Typed, source-labelled scalar inputs shared by contracts and power estimates."""
import json
import math
from pathlib import Path
from tools.core.common import KitError, sha256

STATUSES = {'guaranteed', 'typical', 'assumed', 'measured'}
UNITS = {'V', 'A', 'ohm', 'ratio', 'mm'}


def number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise KitError('%s must be a finite number (not a boolean)' % label)
    return float(value)


class Assumptions:
    def __init__(self, project):
        self.path = Path(project).resolve() / 'hardware/interfaces/assumptions.json'
        raw = self.path.read_bytes()
        import hashlib
        self.digest = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('assumptions'), list):
            raise KitError('Expected assumptions.json schema 1 with assumptions array')
        self.records, self.used = {}, set()
        for record in data['assumptions']:
            if not isinstance(record, dict) or not isinstance(record.get('id'), str) or not record['id'].strip():
                raise KitError('Each assumption needs a nonempty id')
            key = record['id']
            if key in self.records:
                raise KitError('Duplicate assumption id: ' + key)
            number(record.get('value'), key)
            if (not isinstance(record.get('unit'), str) or record['unit'] not in UNITS
                    or not isinstance(record.get('status'), str) or record['status'] not in STATUSES):
                raise KitError('Invalid unit/status for assumption: ' + key)
            for field in ('source', 'revision', 'conditions'):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    raise KitError('%s needs %s (use explicit rationale/revision for assumptions)' % (key, field))
            self.records[key] = record

    def get(self, key, unit, minimum=0, strict=False):
        if not isinstance(key, str) or key not in self.records:
            raise KitError('Unresolved assumption reference: %r' % key)
        record = self.records[key]
        if record['unit'] != unit:
            raise KitError('%s: expected %s, got %s' % (key, unit, record['unit']))
        value = number(record['value'], key)
        if value < minimum or (strict and value == minimum):
            raise KitError('%s is outside the allowed range' % key)
        self.used.add(key)
        return value

    def basis(self):
        return {'inputs': [self.records[k] for k in sorted(self.used)],
                'contains_non_guaranteed_inputs': any(self.records[k]['status'] != 'guaranteed' for k in self.used),
                'assumptions_sha256': self.digest,
                'scope': 'source/status declarations are not independently verified; calculations are estimates'}

    def unchanged(self):
        if sha256(self.path) != self.digest:
            raise KitError('Assumptions changed during calculation; discard the run')


def check(project):
    register = Assumptions(project)
    return {'status': 'PASS' if register.records else 'INCOMPLETE', 'records': list(register.records.values()),
            'scope': 'input format and provenance completeness only; no datasheet or measurement validation',
            'assumptions_sha256': register.digest}
