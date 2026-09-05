"""Allow ``python -m faceproof`` as an alias for ``python -m faceproof.cli``."""

import sys

from faceproof.cli import main

if __name__ == "__main__":
    sys.exit(main())
