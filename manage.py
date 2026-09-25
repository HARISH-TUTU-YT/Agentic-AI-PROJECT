#!/usr/bin/env python
import os
import sys

def main():
    """Forward command to Django backend in back/back."""
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "back", "back")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InventoryCore.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()
