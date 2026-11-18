import sys
import os

# Ensure the repo root is on sys.path so `lambdas.extractor.*` imports resolve.
repo_root = os.path.dirname(__file__)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Also add the extractor directory itself so that handler.py's bare imports
# (from confluence_client import ..., from text_processing import ...) resolve
# when the module is loaded as lambdas.extractor.handler during testing.
extractor_dir = os.path.join(repo_root, "lambdas", "extractor")
if extractor_dir not in sys.path:
    sys.path.insert(0, extractor_dir)
