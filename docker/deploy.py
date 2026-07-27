# XXX copy image_xxx values (as needed) to settings!!!
# XXX check for missing settings!!!
# XXX export select settings to docker_env

"""
mc-deploy script for sous-chef-kitchen API stack
started 7/25/2026

from shell version 7/2025 and story-indexer deploy.py script 7/2026;
both from story-indexer/docker/deploy.sh 9/2023;
from rss-fetcher/dokku-scripts/push.sh 9/2022!
"""

import os
import sys

# mc-deploy package (in mediacloud/system-dev-ops repo):
from mc_deploy.base import CmdArgs, CmdParser, ParserArgs
from mc_deploy.docker import DockerDeploy
from mc_deploy.pyproject import PyProjectMixin

SUPER_VERBOSE = False  # for debug


# MUST match compose file container name (cannot be interpolated)!!
# hostname! no underscores!
PREFECT_CONTAINER_NAME = "prefect-server"


class SousChefKitchenDeploy(PyProjectMixin, DockerDeploy):
    IMAGE_NAME = "notused"  # see docker_image_name below
    IMAGE_REPO = "mcsystems"
    INST_BASE = "kitchen"  # stack base name

    PREFECT_FILE = "prefect.yaml"  # base name; use self.prefect_file!

    REPO_NAME = "sous-chef-kitchen"

    # for looking up development sous-chef-ref
    # also appears in Dockerfile (as git+https for pip) pass as an ARG??
    SOUS_CHEF_PUBLIC = "https://github.com/mediacloud/sous-chef.git"

    def airtable_version(self) -> str:
        if self.is_prod():
            return self.tag  # version
        else:
            return self.image_tag

    def deploy_default_settings(self, args: CmdArgs) -> None:  # noqa: C901
        """
        called before deploy_cmd_helper to set defaults
        before settings files loaded
        """

        # Set most variables used in deploy.yaml here
        # PLEASE try to keep alphabetical to avoid duplicates/confusion,
        # and prefix with name of component the variable applies to!

        self.settings_add("KITCHEN_DEPLOYMENT_NAME", "kitchen-base")
        # KITCHEN_IMAGE set later
        # KITCHEN_IMAGE_TAG set later
        # KITCHEN_IMAGE_NAME set later

        kitchen_port = 8000  # native port (inside stack)
        self.settings_add("KITCHEN_PORT", str(kitchen_port))

        # port published *on docker host* using deployment-type bias:
        self.settings_add("KITCHEN_PORT_PUBLISHED", str(kitchen_port + self.port_bias))

        # NETWORK_NAME set later

        self.settings_add("PREFECT_CONTAINERS", "1")

        self.prefect_file = os.path.join(self.deploy_dir, self.PREFECT_FILE)
        # Interpolated and then built into the kitchen image
        self.settings_add("PREFECT_FILE", self.prefect_file)

        prefect_port = 4200  # native port (inside stack)
        self.settings_add("PREFECT_PORT", str(prefect_port))

        # calculate published port numbers using deployment-type bias:
        self.settings_add("PREFECT_PORT_PUBLISHED", str(prefect_port + self.port_bias))

        # PREFECT_WORKER_IMAGE set later

        # Keep prefect server on official image.
        self.settings_add("PREFECT_SERVER_IMAGE", "prefecthq/prefect:3-latest")

        prefect_url = "http://{PREFECT_CONTAINER_NAME}:{prefect_port}/api"
        self.settings_add("PREFECT_URL", prefect_url)

        # used multiple places: might vary if multiple deployments
        # sharing uncontainered prefect server?
        self.settings_add("PREFECT_WORK_POOL_NAME", "kitchen-work-pool")

        sha, ref = self.sous_chef_sha_ref(args.sous_chef_ref)
        self.settings_add("SOUS_CHEF_REF", ref)
        self.settings_add("SOUS_CHEF_SHA", sha)

    def docker_compose_file_create(self) -> None:
        # doesn't create compose file!

        # here after inst_name settled, image_tag set,
        # CANNOT be overridden by settings files:
        self.settings_add("KITCHEN_IMAGE_NAME", self.docker_image_name())
        self.settings_add("KITCHEN_IMAGE", self.docker_image_full())
        self.settings_add("KITCHEN_IMAGE_TAG", self.image_tag)

        # allow multiple deploys on same swarm/cluster:
        self.settings_add("NETWORK_NAME", self.inst_name)

        self.settings_add("PREFECT_WORKER_IMAGE", self.docker_image_full("-worker"))

        # ################ interpolate prefect.yaml.in

        prefect_in_file = self.prefect_file + ".in"

        with open(prefect_in_file) as fin:
            prefect_file = fin.read()

        def repl(subj, value):
            nonlocal prefect_file
            assert value
            # print("repl", subj, value)
            prefect_file = prefect_file.replace(subj, value)

        def repl_setting(subject_string, setting_name=None):
            if setting_name is None:
                setting_name = subject_string
            replacement = self.settings[setting_name]
            repl(subject_string, replacement)

        # things in settings:
        repl_setting("DEPLOYMENT_NAME", "KITCHEN_DEPLOYMENT_NAME")
        repl_setting("PREFECT_WORKER_IMAGE")
        repl_setting("WORK_POOL_NAME", "PREFECT_WORK_POOL_NAME")

        # not in settings (not used in compose file)
        remote = self.git_origin_remote()
        repl("GIT_REPO", self.git_public_url(remote))
        repl("GIT_TAG", self.tag)

        try:
            os.unlink(self.prefect_file)
        except OSError:
            pass
        print("writing", self.PREFECT_FILE)
        with open(self.prefect_file, "w") as fout:
            self.fix_file_owner(fout, False)  # owned by user; not private
            fout.write(prefect_file)

    def docker_image_name(self) -> str:
        # You GET an image name, and YOU get an image name!
        return self.inst_name

    def docker_image_repo(self) -> str:
        # overridden to always return external registry
        # XXX empty unless production??
        return self.IMAGE_REPO

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

    def sous_chef_sha_ref(self, ref: str) -> tuple[str, str]:
        sha = ""
        if ref:
            if self.is_prod_staging():
                self.warning(f"ignoring sous-chef-ref {ref} for {self.branch}")
                ref = ""
            else:
                # XXX make an mc_deploy.BaseDeploy method??
                line = self.proc_output_one(
                    ["git", "ls-remote", self.SOUS_CHEF_PUBLIC, ref]
                )
                if line:
                    sha = line.split()[0]
                if not sha:
                    self.fatal(f"could not find git hash for sous-chef-ref {ref}")
        return (sha, ref)

    # ############### commands

    def deploy_cmd_init(self, cp: CmdParser) -> None:
        super().deploy_cmd_init(cp)

        # XXX _could_ take default from environment SOUS_CHEF_REF
        # (would better reflect shell script behavior)
        cp.add_argument(
            "-s",
            "--sous-chef-ref",
            default="",
            help="sous-chef git ref for development only",
        )

    def deploy_cmd_helper(self, args: CmdArgs) -> None:
        super().deploy_cmd_helper(args)  # load config

        if SUPER_VERBOSE:
            print("======== settings")
            for key, val in self.settings.items():
                print(key, val)

        # XXX run "exp" here to put vars in docker environment
        # XXX pass DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 ??????


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
