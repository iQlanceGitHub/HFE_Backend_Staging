# config_local.py

# Override the LOG_FILE to a directory where the user has write permissions
import os

LOG_FILE = os.path.expanduser("~/.pgadmin/pgadmin4.log")
