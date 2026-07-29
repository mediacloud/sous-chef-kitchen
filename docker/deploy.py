"""
mc-deploy script for sous-chef-kitchen API stack
started 7/25/2026

from shell version 7/2025 and story-indexer deploy.py script 7/2026;
both from story-indexer/docker/deploy.sh 9/2023;
from rss-fetcher/dokku-scripts/push.sh 9/2022!
"""

import os
import sys
import urllib.parse

# mc-deploy package (in mediacloud/system-dev-ops repo):
from mc_deploy.base import CmdArgs, CmdParser, ParserArgs
from mc_deploy.docker import DockerDeploy, TransferCheck, TransferVar
from mc_deploy.pyproject import PyProjectMixin

SUPER_VERBOSE = False  # for debug


# MUST match compose file container names (cannot be interpolated)!!
# hostnames, so no underscores!
PREFECT_CONTAINER_NAME = "prefect-server"
PREFECT_POSTGRES = "prefect-postgres"

# settings interpolated in docker-compose.yml file (via environment vars)
# should be prefixed with the name of the component they apply to!!!

# NOTE! failure to export a variable may result in cryptic
# error message "read: ..../docker is dir"

XV = TransferVar
XC = TransferCheck
DOCKER_SETTINGS = [
    # Entries in this list are BY DEFINITION transferred
    # from "settings" to the environment passed to docker
    # build and compose commands.
    # PLEASE keep in alphabetical order to avoid duplicates!!
    # "B2" settings should be compatible with any S3-like endpoint!
    XV("B2_APP_KEY", check=XC.PROD),
    XV("B2_BUCKET", check=XC.PROD),
    XV("B2_KEY_ID", check=XC.PROD),
    XV("B2_S3_ENDPOINT", check=XC.PROD),
    XV("KITCHEN_DEPLOYMENT_NAME", default="kitchen-base"),
    XV("KITCHEN_IMAGE"),
    XV("KITCHEN_PORT", check=XC.INT, default="8000"),  # inside stack
    # port published *on docker host* using deployment-type bias:
    XV("KITCHEN_PORT_PUBLISHED", check=XC.INT),
    # Email Server Creds:
    XV("GMAIL_APP_USERNAME", check=XC.PROD),
    XV("GMAIL_APP_PASSWORD", check=XC.PROD),
    XV("GROQ_API_KEY", check=XC.PROD),  # LLMs
    XV("HUGGINGFACE_API_KEY", check=XC.PROD),  # LLMs
    XV("MEDIACLOUD_API_KEY", check=XC.PROD),
    XV("NETWORK_NAME"),  # set later
    XV("PREFECT_API_DATABASE_CONNECTION_URL"),
    XV("PREFECT_CONTAINERS", check=XC.INT, default="1"),
    XV("PREFECT_PORT", check=XC.INT, default="4200"),  # inside stack
    XV("PREFECT_PORT_PUBLISHED", check=XC.INT),  # biased
    XV("PREFECT_POSTGRES_DB", default="prefect"),
    XV("PREFECT_POSTGRES_PASSWORD"),
    XV("PREFECT_POSTGRES_USER", default="prefect"),
    # user official image for prefect server:
    XV("PREFECT_SERVER_IMAGE", default="prefecthq/prefect:3-latest"),
    XV("PREFECT_URL"),
    XV("PREFECT_WORKER_IMAGE"),
    XV("PREFECT_WORK_POOL_NAME", default="kitchen-work-pool"),  # multiple places
    # XV("PRIVATE_CONF_FILE"),   # env-file path: read by docker
    XV("SC_MAX_USER_FLOWS", check=XC.INT, default="1"),  # max flows per user
    XV("SOUS_CHEF_REF", check=XC.ALLOW_EMPTY),
    XV("SOUS_CHEF_SHA", check=XC.ALLOW_EMPTY),
    # PLEASE keep in alphabetical order to avoid duplicates!!
]


class SousChefKitchenDeploy(PyProjectMixin, DockerDeploy):
    IMAGE_NAME = "notused"  # see docker_image_name method below
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
        before settings files loaded.

        NOTE! inst_name not yet set!
        """

        # get defaults for values passed to docker:
        self.settings_defaults(DOCKER_SETTINGS)

        # DOCKER_SETTINGS out in global vars, things here need to be
        # set at runtime once instance type etc known.

        # calculate published port numbers using deployment-type bias
        # (set in BaseDeploy.deply_cmd_helper) based on default values
        # set in DOCKER_SETTINGS.
        kitchen_port = int(self.settings["KITCHEN_PORT"] or "")
        self.settings_add("KITCHEN_PORT_PUBLISHED", str(kitchen_port + self.port_bias))

        self.prefect_file = os.path.join(self.deploy_dir, self.PREFECT_FILE)
        # Interpolated and then built into the kitchen image
        self.settings_add("PREFECT_FILE", self.prefect_file)

        prefect_port = int(self.settings["PREFECT_PORT"] or "")
        self.settings_add("PREFECT_PORT_PUBLISHED", str(prefect_port + self.port_bias))

        if self.is_dev():
            self.settings_add("PREFECT_POSTGRES_PASSWORD", "devprefectlocal")

        prefect_url = "http://{PREFECT_CONTAINER_NAME}:{prefect_port}/api"
        self.settings_add("PREFECT_URL", prefect_url)

        sha, ref = self.sous_chef_sha_ref(args.sous_chef_ref)
        self.settings_add("SOUS_CHEF_REF", ref)
        self.settings_add("SOUS_CHEF_SHA", sha)

    def docker_compose_file_create(self) -> None:
        # doesn't create compose file (uses $ENV interpolation)

        def get(var: str) -> str:
            val = self.settings.get(var) or ""
            if not val:
                self.fatal(f"{var} not set")
            return val

        def get_enc(var: str) -> str:
            return urllib.parse.quote(get(var), safe="")

        pw = get_enc("PREFECT_POSTGRES_PASSWORD")
        user = get_enc("PREFECT_POSTGRES_USER")
        db = get("PREFECT_POSTGRES_DB")  # wasn't encoded in deploy.sh

        url = f"postgresql+asyncpg://{user}:{pw}@{PREFECT_POSTGRES}:5432/{db}"
        self.settings_add("PREFECT_API_DATABASE_CONNECTION_URL", url)

        # transfer settings to docker environment
        self.settings_docker(DOCKER_SETTINGS)

        # ################ interpolate prefect.yaml.in

        prefect_in_file = self.prefect_file + ".in"

        # was using sed; file is small so deal with it internally,
        # using brute force (multiple passes over file contents)
        # avoids changing file during development of this script.

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

        # NOTE!!! If any secrets added here, make file private
        # in fix_file_owner call below!

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

        defref = os.environ.get("SOUS_CHEF_REF", "")
        cp.add_argument(
            "-S",
            "--sous-chef-ref",
            default=defref,
            help="sous-chef git ref for development only",
        )

    def deploy_cmd_helper(self, args: CmdArgs) -> None:
        super().deploy_cmd_helper(args)  # load config

        # NOTE! Values set here CANNOT be overridden by settings files

        # inst_name not set until BaseDeploy.deploy_cmd_helper returns:
        # allow multiple deploys on same swarm/cluster:
        self.settings_add("NETWORK_NAME", self.inst_name)

        # here after image_tag set:
        self.settings_add("KITCHEN_IMAGE_NAME", self.docker_image_name())
        self.settings_add("KITCHEN_IMAGE", self.docker_image_full())
        self.settings_add("KITCHEN_IMAGE_TAG", self.image_tag)

        self.settings_add("PREFECT_WORKER_IMAGE", self.docker_image_full("-worker"))

        if SUPER_VERBOSE:
            print("======== settings")
            for key, val in self.settings.items():
                print(key, val)


d = SousChefKitchenDeploy()
sys.exit(d.run())
