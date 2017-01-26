import re
from collections import deque
from six import python_2_unicode_compatible, text_type
from jsonschema import exceptions as schema_exceptions
from . import enums
from .util import CHECK_CODES


class JSONError(schema_exceptions.ValidationError):
    """Wrapper for errors thrown by iter_errors() in the jsonschema module.
    Makes errors generated by our functions look like those from jsonschema.
    """
    def __init__(self, msg=None, instance_id=None, check_code=None):
        if check_code is not None:
            # Get code number code from name
            code = list(CHECK_CODES.keys())[list(CHECK_CODES.values()).index(check_code)]
            msg = '{%s} %s' % (code, msg)
        super(JSONError, self).__init__(msg, path=deque([instance_id, 0]))


class NoJSONFileFoundError(OSError):
    """Represent a problem finding the input JSON file(s).

    """
    pass


class ValidationError(Exception):
    """Base Exception for all validator-specific exceptions. This can be used
    directly as a generic Exception.
    """
    pass


class SchemaInvalidError(ValidationError):
    """Represent an error with the JSON Schema file itself.

    """
    pass


@python_2_unicode_compatible
class SchemaError(ValidationError):
    """Represent a JSON Schema validation error.

    Args:
        error: An error returned from JSON Schema validation.

    Attributes:
        message: The JSON validation error message.

    """
    def __init__(self, error):
        super(SchemaError, self).__init__()

        if error:
            self.message = text_type(error)
        else:
            self.message = None

    def as_dict(self):
        """Returns a dictionary representation.
        """
        return {'message': self.message}

    def __str__(self):
        return text_type(self.message)


def pretty_error(error, verbose=False):
    """Return an error message that is easier to read and more useful.
    """
    error_loc = ''
    try:
        error_loc = error.instance['id'] + ': '
    except (TypeError, KeyError):
        if error.path:
            while len(error.path) > 0:
                path_elem = error.path.popleft()
                if type(path_elem) is not int:
                    error_loc += path_elem
                elif len(error.path) > 0:
                    error_loc += '[' + text_type(path_elem) + ']/'
            error_loc += ': '

    # Get error message and remove ugly u'' prefixes
    if verbose:
        msg = text_type(error)
    else:
        msg = error.message
    msg = re.sub(r"(^| )(|\[|\(|\{)u'", r"\g<1>\g<2>'", msg)

    # Don't reword error messages from our validators,
    # only the default error messages from the jsonschema library
    if repr(error.schema) == '<unset>':
        return error_loc + msg

    # Reword error messages containing regexes
    if error.validator == 'pattern' and 'title' in error.schema:
        if error.schema['title'] == 'type':
            msg = re.sub(r"match '.+'$", 'match the \'type\' field format '
                         '(lowercase ASCII a-z, 0-9, and hypens only - and no '
                         'two hyphens in a row)', msg)
        elif error.schema['title'] == 'identifier':
            msg = re.sub(r"match '.+'$", 'match the id format '
                         '([object-type]--[UUIDv4])', msg)
        elif error.schema['title'] == 'id':
            msg = re.sub(r"match '.+'$", 'start with \'' +
                         error.validator_value[1:-2] + '--\'', msg)
        elif error.schema['title'] == 'timestamp':
            msg = re.sub(r"match '.+'$", 'match the timestamp format '
                         '(YYYY-MM-DDTHH:mm:ss[.s+]Z)', msg)
        elif error.schema['title'] == 'relationship_type':
            msg = re.sub(r"does not match '.+'$", 'contains invalid '
                         'characters', msg)
        elif error.schema['title'] == 'url':
            msg = re.sub(r"match '.+'$", 'match the format '
                         'of a URL', msg)
    # Reword 'is not valid under any of the given schemas' errors
    elif type(error.instance) is list and len(error.instance) == 0:
        msg = re.sub(r"\[\] is not valid .+$", 'empty arrays are not allowed',
                     msg)
    # Reword custom property errors
    elif 'title' in error.schema and error.schema['title'] == 'core':
        if error.validator == 'additionalProperties':
            msg = re.sub(r"Additional .+$", 'Custom properties must match the '
                         'proper format (lowercase ASCII a-z, 0-9, and '
                         'underscores; 3-250 characters)', msg)
        elif error.validator == 'not' and 'anyOf' in error.validator_value:
            msg = re.sub(r".+", "Contains a reserved property ('%s')"
                         % "', '".join(enums.RESERVED_PROPERTIES), msg)
    # Reword external reference error
    elif error.validator == 'oneOf':
        if 'external_references' in error.schema_path:
            msg = "If the external reference is a CVE, 'source_name' must be" \
                  " 'cve' and 'external_id' must be in the CVE format " \
                  "(CVE-YYYY-NNNN+). If the external reference is a CAPEC, " \
                  "'source_name' must be 'capec' and 'external_id' must be " \
                  "in the CAPEC format (CAPEC-N+)."
    # Reword forbidden enum value errors
    elif error.validator == 'not':
        if 'enum' in error.validator_value:
            msg = re.sub(r"\{.+\} is not allowed for '(.+)'$", r"'\g<1>' is "
                         "not an allowed value", msg)
        elif ('target_ref' in error.schema_path or
              'source_ref' in error.schema_path):
                msg = ("Relationships cannot link bundles, marking definitions"
                       ", sightings, or other relationships. This field must "
                       "contain the id of an SDO.")
    elif error.validator == 'anyOf' or error.validator == 'oneOf':
        msg = msg + ':\n' + text_type(error.schema)

    return error_loc + msg
