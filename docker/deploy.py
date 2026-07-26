"""
mc-deploy script for sous-chef-kitchen started 7/25/2026
from mc-deploy script for story-indexer started 7/11/2026
from deploy.sh started 9/2023
from rss-fetcher/dokku-scripts/push.sh 9/2022!
"""

import sys

# mc-deploy package (in mediacloud/system-dev-ops repo):
from mc_deploy.base import CmdArgs, CmdParser, ParserArgs
from mc_deploy.docker import DockerDeploy
from mc_deploy.pyproject import PyProjectMixin

SUPER_VERBOSE = False  # for debug


class SousChefKitchenDeploy(PyProjectMixin, DockerDeploy):
    INST_BASE = "kitchen"  # stack base name
    REPO_NAME = "sous-chef-kitchen"
    SOUS_CHEF_PUBLIC = "https://github.com/mediacloud/sous-chef.git"

    def airtable_version(self):
        if self.is_prod():
            return self.tag
        else:
            return self.image_tag  # ???

    def deploy_default_settings(self, args: CmdArgs) -> None:  # noqa: C901
        """
        called before deploy_cmd_helper to set defaults
        before settings files loaded
        """

        sha = ""
        if ref := args.sous_chef_ref:
            if self.is_prod_staging():
                self.warning(f"ignoring sous-chef-ref {ref} for {self.branch}")
                ref = ""
            else:
                line = self.proc_output_one(
                    ["git", "ls-remote", self.SOUS_CHEF_PUBLIC, ref]
                )
                if line:
                    sha = line.split()[0]
                if not sha:
                    self.fatal(f"could not find git hash for sous-chef-ref {ref}")

        self.settings_add("KITCHEN_PORT", "8000")  # native port (inside stack)
        self.settings_add("PREFECT_PORT", "4200")  # native port (inside stack)
        self.settings_add("SOUS_CHEF_REF", ref)
        self.settings_add("SOUS_CHEF_SHA", sha)

    def settings_get_new(self, args: ParserArgs) -> None:
        """
        load project settings; called from deploy_cmd_helper
        """
        super().settings_get_new(args)
        assert not self._conf_loaded
        self.deploy_default_settings(args)  # before loading files

        if self.is_prod_staging():
            self.settings_load_private_files(self.PROJECT_REPO, [".env"])
            self.settings_load_private_files("management", ["env.sh"])
        else:
            # XXX test if it exists??
            self.settings_load_file(".env")

    # ############### commands

    def deploy_cmd_init(self, cp: CmdParser) -> None:
        super().deploy_cmd_init(cp)

        # XXX _could_ take default from environment SOUS_CHEF_REF
        cp.add_option(
            "-s", "--sous-chef-ref", help="sous-chef git ref for development only"
        )

    def deploy_cmd_helper(self, args: CmdArgs) -> None:
        super().deploy_cmd_helper(args)  # load config

        if SUPER_VERBOSE:
            print("======== settings")
            for key, val in self.settings.items():
                print(key, val)

        # XXX run "exp" here to put vars in docker environment
        # XXX pass DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 ??????
        # XXX create prefect.yaml


d = SousChefKitchenDeploy()
sys.exit(d.run())

"""
# Check and export variables interpolated in $COMPOSE_FILE.
# Values should be set above here, and should be prefixed
# with the name of the component they apply to!

# PLEASE keep in alphabetical order to avoid duplicates
# NOTE! failure to export a variable may result in cryptic
# error message "read: ..../docker is dir"
exp KITCHEN_DEPLOYMENT_NAME
exp KITCHEN_IMAGE
exp KITCHEN_PORT int
exp KITCHEN_PORT_PUBLISHED int

exp NETWORK_NAME

exp PREFECT_API_DATABASE_CONNECTION_URL
exp PREFECT_CONTAINERS
exp PREFECT_PORT int
exp PREFECT_PORT_PUBLISHED int
exp PREFECT_POSTGRES_DB
exp PREFECT_POSTGRES_PASSWORD
exp PREFECT_POSTGRES_USER
exp PREFECT_SERVER_IMAGE
exp PREFECT_URL
exp PREFECT_WORKER_IMAGE
exp PREFECT_WORK_POOL_NAME	# used multiple places

exp PRIVATE_CONF_FILE
exp SC_MAX_USER_FLOWS int	# max flows per user (defaults to 1)
exp SOUS_CHEF_REF allow-empty
exp SOUS_CHEF_SHA allow-empty
"""
