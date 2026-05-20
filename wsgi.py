print('IMPORTING: wsgi.py', flush=True)

from app import create_app

app = create_app()