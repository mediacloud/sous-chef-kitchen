#!/usr/bin/env python3

"""
Interact with the Sous Chef Kitchen via the command line.
"""

from sous_chef_kitchen.client.cli import cli

if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        pass
