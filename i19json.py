#!/usr/bin/env python

"""
Compile gettext po file into json
"""

import sys
import json
from cPickle import load
import re
from logging import warn, info, getLogger

from babel.messages.pofile import read_po


# Match variables or nested i19-name tags
# TODO broader regex
# ${match}
INCLUDES = re.compile('(\$\{[\w\-\.]*\})')
# {{match}}
ANGULAR = re.compile('(\{\{[\w\-\.\(\)]*\}\})')

# Match plural number and expression in PO header
PLURAL_FORMS = re.compile('^nplurals=(\d+); plural=(.*)$')

def add_includes(msgstring, cache):
    """
    Replace all ${include_name} in msgstring with respective cache[include_name]
    """
    for var in INCLUDES.findall(msgstring):
        if not var in cache:
            warn("Invalid i19i identifier: %s", var)
        else:
            msgstring = msgstring.replace(var, cache[var])
    return msgstring


def _contains(src, dst, msg, msgid):
    """
    Check if all of items in `src` are also available in `dst`
    emit warning `msg` otherwise
    Used by `validate_message`
    """
    result = True
    for val in src:
        if not val in dst:
            result = False
            warn(msg, val, msgid)
    return result

def validate_message(translation, original, msgid, skip_missing_var=False):
    """
    Warn on all newly introduced or missing variables or references in the
    translation
    """
    org_inc = INCLUDES.findall(original)
    org_var = ANGULAR.findall(original)
    tr_inc = INCLUDES.findall(translation)
    tr_var = ANGULAR.findall(translation)

    return (
            _contains(org_inc, tr_inc,
                    "Translation misses reference %s in %r", msgid) and
            (skip_missing_var or _contains(org_var, tr_var,
                    "Translation misses variable %s in %r", msgid)) and
            _contains(tr_inc, org_inc,
                    "Translation introduces reference %s in %r", msgid) and
            _contains(tr_var, org_var,
                    "Translation introduces variable %s in %r", msgid)
            )


def catalog2dict(catalog, cache_file, __stats = [0, 0],):
    """Convert PO catalog to dict suitable for JSON serialization"""

    with file(cache_file) as caf:
        include_cache, original_strings = load(caf)

    def single(msg_id, msg_str, skip_check=False):
        """Convert a single message string"""
        __stats[0] += 1
        default = original_strings[msg_id][1]
        if validate_message(msg_str, default, msg_id, skip_check) and msg_str:
            __stats[1] += 1
            return add_includes(msg_str, include_cache)
        else:
            return ''

    def entry(message):
        """Convert a single message ID"""
        if not message.pluralizable:
            return message.id, single(message.id, message.string)
        else:
            return message.id[0], \
                    [single(message.id[0], mstr, i == 0)
                            for i, mstr in enumerate(message.string)]

    return dict([entry(msg) for msg in catalog]), __stats[0], __stats[1]


def extract_plural_func(catalog):
    """Extract nplurals and plural from catalog's Plural-Forms header"""
    forms = dict(catalog.mime_headers)['Plural-Forms']
    return PLURAL_FORMS.match(forms).groups()


def main():
    """
    Usage: i19json SOURCE LOCALE CACHE OUTPUT

      SOURCE po file
      LOCALE locale identifier
      CACHE cache file created by i19extract.py
      OUTPUT JSON file
    """
    assert len(sys.argv) == 5, main.__doc__

    po_file, locale, cache_file, jo_file = sys.argv[1:5]

    getLogger().name = po_file
    getLogger().level = 0

    with file(po_file) as pof:
        catalog = read_po(pof, locale)

    messages, total, translated = catalog2dict(list(catalog)[1:], cache_file)

    info("%s: %d of %d (%d unique) translated (%d%%)",
            jo_file, translated, total,
            len(messages), 100.0 * translated / total,)

    messages['__pluralization_count__'], messages['__pluralization_expr__'] = \
            extract_plural_func(catalog)

    with file(jo_file, 'w') as json_file:
        json.dump({locale: messages}, json_file)


if __name__ == '__main__':
    main()
