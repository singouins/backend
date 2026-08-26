# -*- coding: utf8 -*-

import os
import sys

# CI copies the shared `mongo` package into `ai/mongo` before booting the
# app (see .github/workflows/pipeline-tests.yml), while a local checkout
# only has it at the repo root. Make both resolvable so `import mongo`
# works whether these tests run in CI or from a dev machine.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_AI_DIR = os.path.dirname(_TESTS_DIR)
_REPO_ROOT = os.path.dirname(_AI_DIR)

for _path in (_AI_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)
