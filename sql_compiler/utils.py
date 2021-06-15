from .compilers import SUPPORTED_BACKENDS


def validate_connection(connection):

    """
    Since not all back ends provide a method to compile the SQL together with the params,
    we need to check if the connection for the QuerySet is supported.

    returns the connection if it's valid, otherwise returns None
    """

    backend_name = connection.settings_dict['ENGINE']
    if backend_name in SUPPORTED_BACKENDS:
        return connection


def bytes_to_string(bytes_obj):

    """
    Converts a bytes object to a string.
    """

    return "".join([chr(c) for c in bytes_obj])
