"""python -m channels.api migrate   create the databases and every table the API needs
python -m channels.api serve     run the API on http://127.0.0.1:8000 (set SUPPORT_AGENT_DEV_AUTH=1 to try it)
"""

import os
import sys

import uvicorn

from channels.api import turns
from channels.api.app import create_app
from data import events, migrate

if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "migrate":
        migrate.migrate_all()
        events.apply_schema(migrate.DEFAULT_DATABASES[0])
        turns.apply_schema(migrate.DEFAULT_DATABASES[0])
    elif command == "serve":
        host = os.environ.get("SUPPORT_AGENT_HOST", "127.0.0.1")
        port = int(os.environ.get("SUPPORT_AGENT_PORT", "8000"))
        uvicorn.run(create_app(), host=host, port=port)
    else:
        sys.exit(__doc__)
