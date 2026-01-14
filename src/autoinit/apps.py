"""Module: autoinit.apps

Purpose: Django app configuration for AutoInit.

Key Components:
- AutoinitConfig: Django AppConfig for autoinit app
"""

from django.apps import AppConfig


class AutoinitConfig(AppConfig):
    """Django app configuration for autoinit.

    Purpose: Register autoinit as a Django app.

    Design:
    Minimal configuration - actual init logic is in management commands.
    """

    name = 'autoinit'
    verbose_name = 'AutoInit'
    default_auto_field = 'django.db.models.BigAutoField'
