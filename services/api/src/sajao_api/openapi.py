"""Write the OpenAPI document that the typed TypeScript client is generated from.

Usage: python -m sajao_api.openapi <output path>
"""

import json
import sys
from pathlib import Path

from sajao_api.main import create_app
from sajao_api.settings import Settings


def main() -> None:
    document = create_app(
        Settings(environment="dev", database_url=None, auth_jwks_url=None, auth_issuer=None)
    ).openapi()
    Path(sys.argv[1]).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
