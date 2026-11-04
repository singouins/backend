# -*- coding: utf8 -*-

"""
The Redis function library functions_pa, for the tests.

functions_pa is Lordslair's library, deployed with the databases chart. The
source of truth is singouins/helm (private): fixtures/functions_pa.lua is a
byte-identical copy of the file below at that commit, for the tests and the CI
only (the CI loads it into its Redis service before starting the apps).
To update: copy the file again from helm, then update these constants.
"""

import hashlib
import os

import redis

FUNCTIONS_PA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'fixtures', 'functions_pa.lua')
FUNCTIONS_PA_HELM_PATH = 'singouins-databases/files/redis/functions/functions_pa.lua'
FUNCTIONS_PA_HELM_COMMIT = '4809c81248f55c5ae14d6d7400228c2c274f9d47'
# `git hash-object` of the file at that commit (the blob sha GitHub shows)
FUNCTIONS_PA_HELM_BLOB = '5186b3afa751ccf98f0046cd87f77922eb574c82'
FUNCTIONS_PA_VERSION = 3


def functions_pa_code() -> str:
    with open(FUNCTIONS_PA_FILE, encoding='utf8') as lua:
        return lua.read()


def functions_pa_blob() -> str:
    """ The git blob sha of the copy (a Windows checkout may turn LF into CRLF). """
    with open(FUNCTIONS_PA_FILE, 'rb') as lua:
        content = lua.read().replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob %d\x00' % len(content) + content).hexdigest()


def load_functions_pa(client) -> None:
    """
    FUNCTION LOAD the copy of functions_pa. A server that already has the
    library keeps it (no REPLACE): the version tests check what it runs.
    """
    try:
        client.function_load(functions_pa_code())
    except redis.exceptions.ResponseError as error:
        if 'already exists' not in str(error):
            raise
