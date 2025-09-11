from flask import Blueprint

bp = Blueprint("status", __name__)

from . import routes  # noqa: E402,F401  (register routes)
