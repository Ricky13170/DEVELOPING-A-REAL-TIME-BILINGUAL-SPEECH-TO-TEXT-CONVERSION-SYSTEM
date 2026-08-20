"""Backend package.

Modules are intentionally not eager-imported. This keeps configuration
overrides effective and avoids loading Torch/models when importing config.
"""
