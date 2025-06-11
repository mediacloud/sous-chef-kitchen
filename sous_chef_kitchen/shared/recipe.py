"""
Work with local Sous Chef recipe files and folders.
"""

import os
from pathlib import Path
from typing import List, Tuple

# Using an alternate yaml library capable of extracting comments in order to
# read and parse the recipe descriptions
from ruamel.yaml import YAML

DEFAULT_RECIPES_PATH = Path(os.getcwd()) / "recipes"
RECIPES_PATH = Path(os.getenv("SC_RECIPES_PATH", DEFAULT_RECIPES_PATH))


def get_recipe_names(recipes_path: Path = RECIPES_PATH) -> List[str]:
    """Get a list of available recipes."""

    return [recipe_path.name for recipe_path in get_recipe_folders(recipes_path)]


def get_recipe_info(recipe_folder_path: Path) -> Tuple[str, List[str]]:
    """Get the name and header comment of the provided recipe."""

    recipe_file = recipe_folder_path / "recipe.yaml"
    if not recipe_file.exists():
        raise FileNotFoundError(f"No recipe.yaml found in {recipe_folder_path}.")

    roundtrip_yaml = YAML(typ="rt")
    with open(recipe_file) as f:
        recipe = roundtrip_yaml.load(f)

    try:
        recipe_header = [c.value.strip("#").strip() for c in recipe.ca.comment[1]]
    except (AttributeError, TypeError):
        # No header comments provided in recipe.yaml
        recipe_header = [""]
    finally:
        return (recipe_folder_path.name, recipe_header)


def get_recipe_folder(recipe_name: str, recipes_path: Path = RECIPES_PATH) -> Path:
    """Get and path of an individual recipe folder and validate its structure."""

    recipe_folders = get_recipe_folders(recipes_path)
    recipe_dict = {recipe_path.name: recipe_path for recipe_path in recipe_folders}

    recipe_path = recipe_dict.get(recipe_name)
    if not recipe_path:
        raise ValueError(f"No recipe found named {recipe_name}.")

    _ = get_recipe_info(recipe_path)
    return recipe_path


def get_recipe_folders(recipes_path: Path = RECIPES_PATH) -> List[Path]:
    """Get the paths of available recipe folders."""

    # Any subfolder containing a recipe.yaml file is treated as a recipe folder
    return [path.parent for path in recipes_path.rglob("*/recipe.yaml")]
