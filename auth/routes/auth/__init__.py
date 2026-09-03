# -*- coding: utf8 -*-

from flask_openapi3 import APIBlueprint, Tag

auth_tag = Tag(name="auth", description="Authentication")

# No url_prefix: this blueprint IS the whole auth service (it used to be
# mounted at /auth under the game api's own domain; now it's the root of
# its own service/domain, so routes are /login, /register, etc. directly).
auth_bp = APIBlueprint(
    "auth",
    __name__,
    abp_tags=[auth_tag],
    )

# Each of these registers its route(s) onto auth_bp as an import side
# effect (mirrors the Flask blueprint convention: define the blueprint
# first, then import the modules that decorate routes onto it).
from . import confirm  # noqa: E402,F401
from . import delete  # noqa: E402,F401
from . import forgot_password  # noqa: E402,F401
from . import infos  # noqa: E402,F401
from . import login  # noqa: E402,F401
from . import logout  # noqa: E402,F401
from . import refresh  # noqa: E402,F401
from . import register  # noqa: E402,F401
from . import resend  # noqa: E402,F401
from . import reset_password  # noqa: E402,F401
