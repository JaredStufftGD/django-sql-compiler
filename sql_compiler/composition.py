import re

from django.db.models import Q, QuerySet
from django.db.models.expressions import BaseExpression, Combinable
from django.db.models.manager import BaseManager
from django.db.models.query import RawQuerySet

from . import utils

SLOT_RE = re.compile(r'\((\w+)\)s')

REJECTED_TYPES = (BaseManager, RawQuerySet, BaseExpression, Combinable, Q)


class ComposeResult(tuple):

    """
    The result of compose(): a tuple of exactly two items that unpacks as `sql, params`
    (a str with Django's %s placeholders, and a tuple of params).

    `.alias` is the database alias shared by every queryset in the composition; `.sql` and `.params`
    mirror the two items. Equality with a plain tuple compares only sql and params, not the alias.

    The result is meant for `connections[result.alias].cursor().execute(*result)` (Django's cursor) and
    `Model.objects.raw(*result, using=result.alias)`, not for the raw driver cursor.
    """

    def __new__(cls, sql, params, alias):
        self = tuple.__new__(cls, (sql, params))
        self._alias = alias
        return self

    def __getnewargs__(self):
        return self[0], self[1], self._alias

    @property
    def sql(self):
        return self[0]

    @property
    def params(self):
        return self[1]

    @property
    def alias(self):
        return self._alias


def parse_template(template):

    """
    Splits the template into tokens: ('text', str), ('percent', None) for a literal %% and
    ('slot', name) for %(name)s. Raises ValueError for any other use of %, naming the 0-based
    index of the %.
    """

    tokens = []
    i = 0
    length = len(template)
    while i < length:
        found = template.find('%', i)
        if found == -1:
            tokens.append(('text', template[i:]))
            break
        if found > i:
            tokens.append(('text', template[i:found]))
        following = template[found + 1:found + 2]
        if following == '%':
            tokens.append(('percent', None))
            i = found + 2
        elif following == '(':
            match = SLOT_RE.match(template, found + 1)
            if match is None or not match.group(1).isidentifier():
                raise ValueError(
                    'compose template has a %(...) form other than %(name)s at position {}'.format(found)
                )
            tokens.append(('slot', match.group(1)))
            i = match.end()
        else:
            raise ValueError(
                'compose template has a positional %s or a lone % at position {}; '
                'write a literal % as %%'.format(found)
            )
    return tokens


def compose(template, /, **slots):

    """
    Embeds querysets, other compose() results and plain values in one hand-written SQL template and
    returns a ComposeResult (sql, params) ready for Django's cursor on `result.alias`.

    The template is a str. Only `%(name)s` (name is an identifier) is a slot and `%%` is a literal percent
    sign, copied to the output as `%%` (the sql has Django's %s placeholders, so it is still escaped for
    the cursor). A positional `%s`, a lone `%` or any other `%(...)` form raises ValueError. A `%(name)s`
    inside a SQL string literal is still a slot.

    A QuerySet slot becomes the SQL and params of `sql_and_params(queryset)` for the queryset's own
    database alias; a ComposeResult slot becomes its sql and params; any other value becomes `%s` and is
    appended to the params, so values are never part of the SQL text. Embedded SQL is inserted as is,
    without parentheses; write them in the template. Params follow placeholder order and repeat at every
    use of a slot. All querysets and results must share one database alias; managers, raw querysets,
    Django expressions, Q objects and tuples are rejected with TypeError.

    The template is trusted SQL. Never build it from user input; pass user input as slot values.
    """

    if not isinstance(template, str):
        raise TypeError('compose needs a str template, got {}'.format(type(template).__name__))
    tokens = parse_template(template)
    used = []
    for kind, name in tokens:
        if kind == 'slot' and name not in used:
            used.append(name)
    missing = [name for name in used if name not in slots]
    if missing:
        raise ValueError(
            'compose template names slots that were not passed: {}'.format(
                ', '.join(repr(name) for name in missing)
            )
        )
    unused = sorted(set(slots) - set(used))
    if unused:
        raise ValueError(
            'compose got keyword arguments the template does not use: {}'.format(
                ', '.join(repr(name) for name in unused)
            )
        )
    kinds = {}
    aliases = {}
    for name in used:
        value = slots[name]
        if isinstance(value, ComposeResult):
            kinds[name] = 'result'
            alias = value.alias
        elif isinstance(value, QuerySet):
            kinds[name] = 'queryset'
            alias = value.db
        elif isinstance(value, REJECTED_TYPES):
            raise TypeError('compose slot {!r} cannot hold a {}'.format(name, type(value).__name__))
        elif isinstance(value, tuple):
            raise TypeError(
                'compose slot {!r} holds a tuple; pass the QuerySet or a compose() result itself, '
                'not a (sql, params) pair'.format(name)
            )
        else:
            kinds[name] = 'value'
            continue
        aliases.setdefault(alias, []).append(name)
        if kinds[name] == 'queryset':
            kinds[name] = ('queryset', alias)
    if len(aliases) > 1:
        raise ValueError(
            'compose slots must share one database alias, got {}'.format(
                '; '.join(
                    '{!r}: {}'.format(alias, ', '.join(sorted(names))) for alias, names in sorted(aliases.items())
                )
            )
        )
    if not aliases:
        raise ValueError(
            'compose needs at least one slot holding a QuerySet or a compose() result, '
            'to know the database alias'
        )
    alias = next(iter(aliases))
    pieces = {}
    for name in used:
        value = slots[name]
        kind = kinds[name]
        if kind == 'result':
            pieces[name] = (value[0], tuple(value[1]))
        elif kind == 'value':
            pieces[name] = ('%s', (value,))
        else:
            sql, params = utils.query_sql_and_params(value.query, kind[1])
            pieces[name] = (sql, tuple(params))
    out = []
    params = []
    for kind, content in tokens:
        if kind == 'text':
            out.append(content)
        elif kind == 'percent':
            out.append('%%')
        else:
            sql, piece_params = pieces[content]
            out.append(sql)
            params.extend(piece_params)
    return ComposeResult(''.join(out), tuple(params), alias)
