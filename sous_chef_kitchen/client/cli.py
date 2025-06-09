"""
Interact with the Sous Chef Kitchen via the command line.
"""

import os
from pathlib import Path
from pprint import pprint

import click
import dotenv
from tabulate import tabulate

from sous_chef_kitchen.client.menu import SousChefKitchenAPIClient, API_BASE_URL
from sous_chef_kitchen.shared import recipe
from sous_chef_kitchen.shared.models import SousChefKitchenSystemStatus

DEFAULT_ENV_PATH = Path.cwd() / ".env"


@click.group()
def cli() -> None:
    """Interact with the Sous Chef Kitchen via the command line."""

    pass


@click.group()
def recipes() -> None:
    """Commands for viewing available recipes."""

    pass


@click.command("list")
def recipes_list() -> None:
    """List available recipes."""

    recipe_info = [recipe.get_recipe_info(recipe_path)
        for recipe_path in recipe.get_recipe_folders()]
    
    recipe_rows = ((name, info[0]) for (name, info) in recipe_info)
    click.echo(tabulate(recipe_rows, headers=["Recipe Name", "Description"]))


@click.command("start")
@click.argument("name", required=True)
@click.argument("parameters", nargs=-1)
def recipes_start(name: str, parameters) -> None:
    """Start a Sous Chef recipe."""

    api_client = SousChefKitchenAPIClient()
    recipe_parameters = dict(zip(parameters[::2], parameters[1::2])) #Stack Overflow is still my friend! 
    print(f"Parsed parameters: {recipe_parameters}")
    if api_client.start_recipe(name, recipe_parameters):
        click.echo(f"Recipe {name} started successfully.")
    else:
        click.echo(f"Unable to start recipe {name}.")

@click.command("schema")
@click.argument("name", required=True)
def recipes_schema(name: str) -> None:
    """ Get the parameter schema for a recipe """

    api_client = SousChefKitchenAPIClient()
    schema = api_client.recipe_schema(name)
    if schema:
        click.echo(f"Schema for recipe {name}: \n {schema} ")
    else:
        click.echo(f"Unable to find any schema information for {name}")

@click.group()
def runs() -> None:
    """Commands for managing runs of recipes."""

    pass


@click.command("cancel")
@click.argument("recipe_name", required=True)
@click.argument("run_id", required=True)
def runs_cancel(recipe_name: str, run_id: str) -> None:
    """Cancel a Sous Chef recipe run."""

    api_client = SousChefKitchenAPIClient()
    if api_client.cancel_recipe(recipe_name, run_id):
        click.echo(f"Run {run_id} for recipe {recipe_name} cancelled.")
    else:
        click.echo(f"Unable to cancel run {run_id} for recipe {recipe_name}.")


@click.command("pause")
@click.argument("recipe_name", required=True)
@click.argument("run_id", required=True)
def runs_cancel(recipe_name: str, run_id: str) -> None:
    """Pause a Sous Chef recipe run."""

    api_client = SousChefKitchenAPIClient()
    if api_client.pause_recipe(recipe_name, run_id):
        click.echo(f"Run {run_id} for recipe {recipe_name} paused.")
    else:
        click.echo(f"Unable to pause run {run_id} for recipe {recipe_name}.")


@click.command("resume")
@click.argument("recipe_name", required=True)
@click.argument("run_id", required=True)
def runs_cancel(recipe_name: str, run_id: str) -> None:
    """Resume a Sous Chef recipe run."""

    api_client = SousChefKitchenAPIClient()
    if api_client.resume_recipe(recipe_name, run_id):
        click.echo(f"Run {run_id} for recipe {recipe_name} resumed.")
    else:
        click.echo(f"Unable to resume run {run_id} for recipe {recipe_name}.")


@click.command("inspect")
@click.argument("run_id", required=True)
def runs_inspect(run_id: str) -> None:
    """Inspect the details of the specified Sous Chef run."""

    api_client = SousChefKitchenAPIClient()
    results = api_client.fetch_run_by_id(run_id)
    
    # TODO: Add actual formatting rather than just a pretty print
    pprint(results)


@click.command("artifacts")
@click.argument("run_id", required=True)
def runs_artifacts(run_id:str) -> None:
    """Return the artifacts associated with a run, if any"""
    api_client = SousChefKitchenAPIClient()
    results = api_client.fetch_run_artifacts(run_id)

    pprint(results)

@click.command("list")
@click.option("--all", 'all_', is_flag=True, default=False, show_default=True,
    help="Include all runs in the output, not just current runs.")
def runs_list(all_: bool) -> None:
    """List actively executing or queued Sous Chef runs and their statuses."""

    api_client = SousChefKitchenAPIClient()
    if all_:
        results = api_client.fetch_all_runs()
    else:
        results = api_client.fetch_active_runs()
    
    # TODO: Add actual formatting rather than just a pretty print
    pprint(results)


@click.command("auth")
@click.option("--validate", is_flag=True, default=True, show_default=True,
    help="Test whether the supplied credentials are valid for Sous Chef.")
def auth(validate: bool) -> None:
    """Cache Media Cloud API credentials."""

    api_auth_email = os.getenv("SC_API_AUTH_EMAIL")
    new_api_auth_email_provided = False
    if not api_auth_email:
        api_auth_email = click.prompt("Media Cloud API Auth Email")
        new_api_auth_email_provided = True

    api_auth_key = os.getenv("SC_API_AUTH_KEY")
    new_api_key_provided = False
    if not api_auth_key:
        api_auth_key = click.prompt("Media Cloud API Auth Key")
        new_api_key_provided = True
    
    if validate:
        api_client = SousChefKitchenAPIClient(api_auth_email, api_auth_key)
        auth_status = api_client.validate_auth()
        if not auth_status.authorized:
            click.echo("Error: Unable to validate API credentials. Not caching.")
            exit(1)
        click.echo("Successfully validated API credentials.")

    if new_api_auth_email_provided or new_api_key_provided:
        dotenv_path = dotenv.find_dotenv()
        if not dotenv_path:
            dotenv_path = click.prompt("Path to .env file", default=DEFAULT_ENV_PATH)
        dotenv.set_key(dotenv_path, "SC_API_AUTH_EMAIL", api_auth_email)
        dotenv.set_key(dotenv_path, "SC_API_AUTH_KEY", api_auth_key)
        click.echo("API credentials cached locally for future use.")


@click.command("status")
def system_status() -> None:
    """Check whether the Sous Chef Kitchen API is available and ready."""

    api_client = SousChefKitchenAPIClient()
    system_status = api_client.fetch_system_status()
    system_name = lambda k: SousChefKitchenSystemStatus.model_fields[k].title
    system_ready = lambda v: "Ready" if v else "Not Ready"
    system_rows = [(system_name(k), system_ready(v)) for k,v in system_status]
    click.echo(f"SC_API_BASE_URL: {API_BASE_URL}")
    click.echo(tabulate(system_rows, headers=["System Name", "Status"]))


def _initialize_cli() -> None:
    """Initialize the command line interface."""

    cli.add_command(recipes)
    cli.add_command(runs)

    cli.add_command(auth)
    cli.add_command(system_status)

    recipes.add_command(recipes_list)
    recipes.add_command(recipes_start)
    recipes.add_command(recipes_schema)

    runs.add_command(runs_list)
    runs.add_command(runs_inspect)
    runs.add_comment(runs_artifacts)
    

_initialize_cli()
