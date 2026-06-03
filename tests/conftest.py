import os
import sys

# Make the flat `cldv/` modules importable from tests.
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cldv"),
)
