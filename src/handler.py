import os
import pyodbc

pyodbc.pooling = False

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from mangum import Mangum
from config.asgi import application

TEXT_MIME_TYPES = [
    "application/json",
    "application/javascript",
    "application/xml",
    "application/vnd.api+json",
    "image/svg+xml",
    "text/css",
    "text/csv",
    "text/html",
    "text/javascript",
    "text/plain",
    "text/xml",
]

lambda_handler = Mangum(
    application,
    lifespan="off",
    text_mime_types=TEXT_MIME_TYPES,
)