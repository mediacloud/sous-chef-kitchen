#!/bin/sh

# Deploy sous-chef-kitchen API stack
# Phil Budne, 7/2025
# (from story-indexer/docker/deploy.sh 9/2023)
# (from rss-fetcher/dokku-scripts/push.sh 9/2022!)

# Deploys from currently checked out branch: branches staging and prod are special.

# Normally requires clean repo (all changes checked in), applies a git
# tag, and pushes the tag to github.  The deploy.sh script
# and compose YAML file are covered by the tag.

# works for users in docker group: su(do) not required!

SCRIPT=$0
SCRIPT_DIR=$(dirname $SCRIPT)

# keep created files (which may contain secrets) private:
umask 077

# stack name (suffix if not production)
# indicates application for peaceful coexistence!!
# used in stack service name and container names, so keep short
BASE_STACK_NAME=kitchen
COMPOSE_FILE=$SCRIPT_DIR/docker-compose.yaml

if [ ! -f $COMPOSE_FILE ]; then
    echo cannot find COMPOSE_FILE $COMPOSE_FILE 1>&2
    exit 1
fi

# hostname w/o any domain
HOSTNAME=$(hostname --short)
BRANCH=$(git branch --show-current)

#if ! python3 -m mc-manage.airtable-deployment-update  --help >/dev/null; then
#    echo FATAL: deployment requires an up-to-date venv with pyairtable requirements 1>&2
#    exit 3
#fi

usage() {
    # NOTE! If you change something in this function, run w/ -h
    # and put updated output into README.md file!!!
    echo "Usage: $SCRIPT [options]"
    echo "options:"
    echo "  -b      build image but do not deploy"
    echo "  -B BR   dry run for specific branch BR (ie; staging or prod, for testing)"
    echo "  -d      enable debug output (show environment variables)"
    echo "  -h      output this help and exit"
    echo "  -n      dry-run: do not deploy"
    echo "  -s REF  use sous-chef git ref (branch, tag, or SHA) REF for dev build (must exist in mediacloud/sous-chef)"
    exit 1
}

# if you add an option here, add to usage function above!!!
while getopts abB:dns: OPT; do
   case "$OPT" in
   b) BUILD_ONLY=1;;
   B) NO_ACTION=1; AS_USER=1; BRANCH=$OPTARG;;
   d) DEBUG=1;;
   n) NO_ACTION=1; AS_USER=1;;
   s) SOUS_CHEF_REF=$OPTARG;;
   ?) usage;;		# here on 'h' '?' or unhandled option
   esac
done

# XXX complain if anything extra on command line?

check_sous_chef_ref() {
    if [ -z "${SOUS_CHEF_REF:-}" ]; then
	return 0
    fi

    echo "Checking sous-chef git ref '${SOUS_CHEF_REF}'..."
    if git ls-remote --exit-code https://github.com/mediacloud/sous-chef.git "$SOUS_CHEF_REF" >/dev/null 2>&1; then
	echo "Found sous-chef ref '${SOUS_CHEF_REF}'."
    else
	echo "ERROR: sous-chef git ref '${SOUS_CHEF_REF}' not found on GitHub." 1>&2
	echo "       Make sure it's a valid branch, tag, or SHA in mediacloud/sous-chef." 1>&2
	exit 1
    fi
}

check_sous_chef_ref

SOUS_CHEF_SHA=""
if [ -n "${SOUS_CHEF_REF:-}" ]; then
    SOUS_CHEF_SHA=$(git ls-remote https://github.com/mediacloud/sous-chef.git "$SOUS_CHEF_REF" | awk 'NR==1 {print $1}')
    if [ -z "$SOUS_CHEF_SHA" ]; then
	echo "ERROR: could not resolve sous-chef git ref '${SOUS_CHEF_REF}' to a commit SHA." 1>&2
	exit 1
    fi
    echo "Resolved sous-chef ref '${SOUS_CHEF_REF}' to commit ${SOUS_CHEF_SHA}."
fi

if [ "x$AS_USER" = x -a $(whoami) != root ]; then
    if ! groups | tr ' ' '\n' | fgrep -qx docker; then
       echo must be run as root or member of docker group 1>&2
       exit 1
    fi
fi

# get logged in user (even if su(do)ing)
# (lookup utmp entry for name of tty from stdio)
# will lose if run non-interactively via ssh (no utmp entry) or cron
LOGIN_USER=$(who am i | awk '{ print $1 }')
if [ "x$LOGIN_USER" = x ]; then
    echo could not find login user 1>&2
    exit 1
fi

# script works for users in docker group, as themselves, and under
# su(do).  runs git commands as the logged in user, so root doesn't
# need to have github ssh keys.
WHOAMI=$(whoami)
run_as_login_user() {
    if [ $WHOAMI = root ]; then
	su $LOGIN_USER -c "$*"
    else
	# here as user in docker group
	$*
    fi
}

report_deployment() {
    # Reporting is best-effort; deployment success should not depend on it.
    if ! run_as_login_user "python3 -m mc-manage.airtable-deployment-update --help" >/dev/null 2>&1; then
	echo "WARNING: deployment reporting skipped (mc-manage not available)" 1>&2
	return 0
    fi

    # Reuse private temp dir and clone pattern to fetch env.sh secrets.
    REPORT_CONF_DIR=$SCRIPT_DIR/private-report-conf$$
    rm -rf "$REPORT_CONF_DIR"
    if ! run_as_login_user mkdir "$REPORT_CONF_DIR"; then
	echo "WARNING: deployment reporting skipped (could not create temp dir)" 1>&2
	return 0
    fi
    chmod go-rwx "$REPORT_CONF_DIR"

    REPORT_CWD=$(pwd)
    cd "$REPORT_CONF_DIR" || return 0
    CONFIG_REPO_PREFIX=$(zzz tvg@tvguho.pbz:zrqvnpybhq)
    MGMT_CONFIG_REPO_NAME=$(zzz znantrzrag-pbasvt)
    if ! run_as_login_user "git clone $CONFIG_REPO_PREFIX/$MGMT_CONFIG_REPO_NAME.git" >/dev/null 2>&1; then
	echo "WARNING: deployment reporting skipped (could not clone management-config)" 1>&2
	cd "$REPORT_CWD" || true
	rm -rf "$REPORT_CONF_DIR"
	return 0
    fi

    ENV_SH="$REPORT_CONF_DIR/$MGMT_CONFIG_REPO_NAME/env.sh"
    if [ ! -f "$ENV_SH" ]; then
	echo "WARNING: deployment reporting skipped (missing env.sh)" 1>&2
	cd "$REPORT_CWD" || true
	rm -rf "$REPORT_CONF_DIR"
	return 0
    fi

    # Source in a subshell and print only needed vars as safe KEY=VALUE lines.
    REPORT_ENV=$(sh -c ". \"$ENV_SH\" >/dev/null 2>&1; printf '%s\n' \"AIRTABLE_API_KEY=\${AIRTABLE_API_KEY-}\" \"AIRTABLE_BASE_ID=\${AIRTABLE_BASE_ID-}\"")
    AIRTABLE_API_KEY=$(echo "$REPORT_ENV" | awk -F= '/^AIRTABLE_API_KEY=/{sub(/^AIRTABLE_API_KEY=/,""); print; exit}')
    AIRTABLE_BASE_ID=$(echo "$REPORT_ENV" | awk -F= '/^AIRTABLE_BASE_ID=/{sub(/^AIRTABLE_BASE_ID=/,""); print; exit}')
    cd "$REPORT_CWD" || true
    rm -rf "$REPORT_CONF_DIR"

    if [ "x$AIRTABLE_API_KEY" = x -o "x$AIRTABLE_BASE_ID" = x ]; then
	echo "WARNING: deployment reporting skipped (missing AIRTABLE_API_KEY or AIRTABLE_BASE_ID)" 1>&2
	return 0
    fi

    REPORT_VERSION=$KITCHEN_IMAGE_TAG
    KITCHEN_PYPROJECT_FILE=$SCRIPT_DIR/../pyproject.toml
    if [ -f "$KITCHEN_PYPROJECT_FILE" ]; then
	PYPROJECT_VERSION=$(awk -F'"' '/^[[:space:]]*version[[:space:]]*=/ { print $2; exit }' "$KITCHEN_PYPROJECT_FILE")
	if [ "x$PYPROJECT_VERSION" != x ]; then
	    REPORT_VERSION=$PYPROJECT_VERSION
	else
	    echo "WARNING: could not parse package version from $KITCHEN_PYPROJECT_FILE; using image tag" 1>&2
	fi
    else
	echo "WARNING: $KITCHEN_PYPROJECT_FILE not found; using image tag as version" 1>&2
    fi

    if ! run_as_login_user "AIRTABLE_API_KEY='$AIRTABLE_API_KEY' AIRTABLE_BASE_ID='$AIRTABLE_BASE_ID' python3 -m mc-manage.airtable-deployment-update --codebase 'sous-chef-kitchen' --name '$STACK_NAME' --env '$DEPLOY_TYPE' --version '$REPORT_VERSION' --hardware '$HOSTNAME'"; then
	echo "WARNING: deployment reporting failed (non-fatal)" 1>&2
    fi
    return 0
}

# report dirty repo
# (used to allow dirty deploys, so this centralized that test)
dirty() {
    echo "$*" 1>&2
    exit 1
}

if ! git diff --quiet; then
    dirty 'local changes not checked in' 1>&2
fi

# defaults for variables that might change based on BRANCH/DEPLOY_TYPE
# (in alphabetical order):

KITCHEN_PORT=8000		# native port (inside stack)
PREFECT_PORT=4200		# native port (inside stack)
#STATSD_REALM="$BRANCH"

# depends on proxy running on tarbell
#STATSD_URL=statsd://stats.tarbell.angwin

# set DEPLOY_TIME, check remotes up to date
case "$BRANCH" in
prod|staging)
    DEPLOY_TYPE="$BRANCH"

    # check if corresponding branch in mediacloud acct up to date

    # get remote for mediacloud account
    # ONLY match ssh remote, since will want to push tag.
    REMOTE=$(git remote -v | awk '/github\.com:mediacloud\// { print $1; exit }')
    if [ "x$REMOTE" = x ]; then
	echo could not find an ssh git remote for mediacloud org repo 1>&2
	exit 1
    fi
    ;;
*)
    DEPLOY_TYPE=dev
    #STATSD_REALM=$LOGIN_USER
    REMOTE=origin
    ;;
esac

# check if in sync with remote
# (send stderr to /dev/null in case remote branch does not exist)
run_as_login_user git fetch $REMOTE $BRANCH 2>/dev/null
if git diff --quiet $BRANCH $REMOTE/$BRANCH -- 2>/dev/null; then
    echo "$REMOTE $BRANCH branch up to date."
else
    dirty "$REMOTE $BRANCH branch not up to date. Run 'git push' first!!"
    # note: push could herald unwelcome news if repos have diverged!
fi

# defaults for staging/dev:
# MUST match compose file container name (cannot be interpolated)!!
PREFECT_CONTAINER_NAME=prefect-server
PREFECT_SERVER=$PREFECT_CONTAINER_NAME
PREFECT_CONTAINERS=1

DATE_TIME=$(date -u '+%F-%H-%M-%S')
TAG=$DATE_TIME-$HOSTNAME-$BRANCH
case $DEPLOY_TYPE in
prod)
    PORT_BIAS=0
    # TEMP OFF (always launch prefect container)
    #PREFECT_CONTAINERS=0
    #PREFECT_SERVER=mediacloud-prefect.angwin
    SENTRY_ENVIRONMENT="production"
    STACK_NAME=$BASE_STACK_NAME

    # could v${PACKAGE_VERSION} if available"
    # rss-fetcher extracts package version and uses that for tag,
    # refusing to deploy if tag already exists.
    TAG=${DATE_TIME}-prod
    ;;
staging)
    PORT_BIAS=10		# ports: prod + 10
    SENTRY_ENVIRONMENT="staging"
    STACK_NAME=staging-$BASE_STACK_NAME
    ;;
dev)
    # pick up from environment, so multiple dev stacks can run on same
    # h/w cluster! Bias can be incremented by one for each new developer
    PORT_BIAS=${KITCHEN_DEV_PORT_BIAS:-20}
    STACK_NAME=${LOGIN_USER}-$BASE_STACK_NAME
    ;;
esac

# use git tag for image tag.
# in development this means old tagged images will pile up until removed
IMAGE_TAG=$(echo $TAG | sed 's/[^a-zA-Z0-9_.-]/_/g')

# Set most variables used in deploy.yaml here
# PLEASE try to keep alphabetical to avoid duplicates/confusion,
# and prefix with name of component the variable applies to!
KITCHEN_DEPLOYMENT_NAME="kitchen-base"

KITCHEN_IMAGE_REPO=mcsystems # XXX local(host) unless production??
KITCHEN_IMAGE_NAME=$STACK_NAME # per-user/deployment type
KITCHEN_IMAGE_TAG=$IMAGE_TAG

KITCHEN_IMAGE=$KITCHEN_IMAGE_REPO/$KITCHEN_IMAGE_NAME:$KITCHEN_IMAGE_TAG
PREFECT_WORKER_IMAGE=$KITCHEN_IMAGE_REPO/$KITCHEN_IMAGE_NAME-worker:$KITCHEN_IMAGE_TAG
# calculate port published *on docker host* using deployment-type bias:
KITCHEN_PORT_PUBLISHED=$(expr $KITCHEN_PORT + $PORT_BIAS)

# allow multiple deploys on same swarm/cluster:
NETWORK_NAME=$STACK_NAME


#Interpolated and then built into the kitchen image
PREFECT_FILE=$SCRIPT_DIR/prefect.yaml
# Keep prefect server on official image.
PREFECT_SERVER_IMAGE=prefecthq/prefect:3-latest
# calculate published port numbers using deployment-type bias:
PREFECT_PORT_PUBLISHED=$(expr $PREFECT_PORT + $PORT_BIAS)
PREFECT_URL=http://$PREFECT_SERVER:$PREFECT_PORT/api
# used multiple places: might vary if multiple deployments sharing prefect server?
PREFECT_WORK_POOL_NAME=kitchen-work-pool


# Add new variables above this line,
# PLEASE keep alphabetical to avoid duplicates/confusion!

PRIVATE_CONF_DIR=$SCRIPT_DIR/private-conf$$
# clean up on exit unless debugging
if [ "x$DEBUG" = x ]; then
    trap "rm -rf $PRIVATE_CONF_DIR $DUMPFILE" 0
fi

zzz() {
    echo $1 | tr 'A-Za-z' 'N-ZA-Mn-za-m'
}

case $DEPLOY_TYPE in
prod|staging|dev)		# TEMP! include dev!!!
    rm -rf $PRIVATE_CONF_DIR
    run_as_login_user mkdir $PRIVATE_CONF_DIR
    chmod go-rwx $PRIVATE_CONF_DIR
    CWD=$(pwd)
    cd $PRIVATE_CONF_DIR
    PRIVATE_CONF_ABS=$(pwd)
    CONFIG_REPO_PREFIX=$(zzz tvg@tvguho.pbz:zrqvnpybhq)
    CONFIG_REPO_NAME=$(zzz fbhf-purs-pbasvt)
    echo cloning $CONFIG_REPO_NAME repo 1>&2
    if ! run_as_login_user "git clone $CONFIG_REPO_PREFIX/$CONFIG_REPO_NAME.git" >/dev/null 2>&1; then
	echo "FATAL: could not clone config repo" 1>&2
	exit 1
    fi
    PRIVATE_CONF_REPO=$PRIVATE_CONF_ABS/$CONFIG_REPO_NAME
    PRIVATE_CONF_FILE=$PRIVATE_CONF_REPO/.env
    echo PRIVATE_CONF_REPO $PRIVATE_CONF_REPO
    echo PRIVATE_CONF_FILE $PRIVATE_CONF_FILE
    cd $CWD
    ;;
dev)
    # relative to COMPOSE_FILE:
    PRIVATE_CONF_FILE=${LOGIN_USER}.env
    ;;
esac

if [ ! -f "$PRIVATE_CONF_FILE" ]; then
    echo PRIVATE_CONF_FILE $PRIVATE_CONF_FILE not found 1>&2
    exit 1
fi

# Load SC_MAX_USER_FLOWS from config file, default to 1 if not set
# Read the value directly from the .env file to avoid sourcing all variables
if grep -q "^SC_MAX_USER_FLOWS=" "$PRIVATE_CONF_FILE" 2>/dev/null; then
    SC_MAX_USER_FLOWS=$(grep "^SC_MAX_USER_FLOWS=" "$PRIVATE_CONF_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'" | xargs)
    # Validate it's a positive integer
    if ! echo "$SC_MAX_USER_FLOWS" | egrep '^[1-9][0-9]*$' >/dev/null 2>&1; then
	echo "WARNING: SC_MAX_USER_FLOWS='$SC_MAX_USER_FLOWS' is not a positive integer, defaulting to 1" 1>&2
	SC_MAX_USER_FLOWS=1
    fi
else
    SC_MAX_USER_FLOWS=1
fi

# Prefect server database: PostgreSQL (compose service prefect-postgres).
# URL is built here so special characters in the password are percent-encoded.
PREFECT_POSTGRES_USER=${PREFECT_POSTGRES_USER:-prefect}
PREFECT_POSTGRES_DB=${PREFECT_POSTGRES_DB:-prefect}
if grep -q "^PREFECT_POSTGRES_PASSWORD=" "$PRIVATE_CONF_FILE" 2>/dev/null; then
    PREFECT_POSTGRES_PASSWORD=$(grep "^PREFECT_POSTGRES_PASSWORD=" "$PRIVATE_CONF_FILE" | cut -d'=' -f2- | sed "s/^[\"']//;s/[\"']$//" | xargs)
elif [ "$DEPLOY_TYPE" = dev ]; then
    PREFECT_POSTGRES_PASSWORD=devprefectlocal
else
    echo "FATAL: PREFECT_POSTGRES_PASSWORD must be set in $PRIVATE_CONF_FILE" 1>&2
    exit 1
fi
PREFECT_POSTGRES_PASSWORD_ENCODED=$(PREFECT_POSTGRES_PASSWORD="$PREFECT_POSTGRES_PASSWORD" python3 -c "import os, urllib.parse; print(urllib.parse.quote(os.environ['PREFECT_POSTGRES_PASSWORD'], safe=''))")
PREFECT_POSTGRES_USER_ENCODED=$(PREFECT_POSTGRES_USER="$PREFECT_POSTGRES_USER" python3 -c "import os, urllib.parse; print(urllib.parse.quote(os.environ['PREFECT_POSTGRES_USER'], safe=''))")
PREFECT_API_DATABASE_CONNECTION_URL="postgresql+asyncpg://${PREFECT_POSTGRES_USER_ENCODED}:${PREFECT_POSTGRES_PASSWORD_ENCODED}@prefect-postgres:5432/${PREFECT_POSTGRES_DB}"

# display things that vary by stack type, from most to least interesting
echo STACK_NAME $STACK_NAME
echo PREFECT_URL $PREFECT_URL
#echo STATSD_REALM $STATSD_REALM

# function to check and export a variable
exp() {
    VAR=$1
    eval VALUE=\$$VAR
    # take optional type second, so lines sortable!
    case $2 in
    bool)
	case $VALUE in
	true|false) ;;
	*) echo "add: $VAR bad bool: '$VALUE'" 1>&2; exit 1;;
	esac
	;;
    int)
	if ! echo $VALUE | egrep '^(0|[1-9][0-9]*)$' >/dev/null; then
	    echo "add: $VAR bad int: '$VALUE'" 1>&2; exit 1
	fi
	;;
    str|'')
	if [ "x$VALUE" = x ]; then
	    echo "add: $VAR is empty" 1>&2; exit 1
	fi
	;;
    allow-empty)
	;;
    *) echo "add: $VAR bad type: '$2'" 1>&2; exit 1;;
    esac
    eval export $VAR
    if [ "x$DEBUG" != x ]; then
	echo ${VAR}=$VALUE
    fi
}

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

#exp STATSD_REALM
#exp STATSD_URL

# add new variables in alphabetical order ABOVE!

DUMPFILE=$COMPOSE_FILE.$TAG
echo "expanding $COMPOSE_FILE as $DUMPFILE" 1>&2
rm -f $DUMPFILE
docker stack config -c $COMPOSE_FILE > $DUMPFILE
STATUS=$?
if [ $STATUS != 0 ]; then
    echo "docker stack config status: $STATUS" 1>&2
    # fails w/ older versions
    if [ $STATUS = 125 ]; then
	echo 'failed due to old version of docker stack command??'
    else
	exit 3
    fi
fi

# XXX check if on suitable server (right swarm?) for prod/staging??

if [ "x$NO_ACTION" != x ]; then
    echo 'dry run: quitting' 1>&2
    exit 0
fi

# XXX display all commits not currently deployed?
# use docker image tag running on stack as base??
echo "Last commit:"
git log -n1

if [ "x$BUILD_ONLY" = x ]; then
    echo ''
    echo -n "Deploy from branch $BRANCH as stack $STACK_NAME? [no] "
    read CONFIRM
    case "$CONFIRM" in
    [yY]|[yY][eE][sS]) ;;
    *) echo '[cancelled]'; exit;;
    esac

    if [ "x$BRANCH" = xprod ]; then
	echo -n "This is production! Type YES to confirm: "
	read CONFIRM
	if [ "x$CONFIRM" != 'xYES' ]; then
	   echo '[cancelled]'
	   exit 0
	fi
    fi
    echo ''
fi

# apply tags before deployment
# (better to tag and not deploy, than to deploy and not tag)
echo adding local git tag $TAG
if run_as_login_user git tag $TAG; then
    echo OK
else
    echo tag failed 1>&2
    exit 1
fi

# push tag to upstream repos
echo pushing git tag $TAG to $REMOTE
if run_as_login_user git push $REMOTE $TAG; then
    echo OK
else
    echo tag push failed 1>&2
    exit 1
fi

# if config elsewhere, tag it too.
if [ -d $PRIVATE_CONF_DIR -a -d "$PRIVATE_CONF_REPO" ]; then
    echo tagging config repo
    if (cd $PRIVATE_CONF_REPO; run_as_login_user git tag $TAG) >/dev/null 2>&1; then
	echo OK
    else
	echo Failed to tag $CONFIG_REPO_NAME 1>&2
	exit 1
    fi
    echo pushing config tag
    if (cd $PRIVATE_CONF_REPO; run_as_login_user git push origin $TAG) >/dev/null 2>&1; then
	echo OK
    else
	echo Failed to push tag to $CONFIG_REPO_NAME 1>&2
	exit 1
    fi
fi

# get non-ssh URL for repo
GIT_REPO=$(git remote get-url $REMOTE | sed 's#git@github.com:#http://github.com/#')
echo GIT_REPO $GIT_REPO

echo "Interpolating prefect.yaml"
sed -e "s/DEPLOYMENT_NAME/$KITCHEN_DEPLOYMENT_NAME/g" \
    -e "s@PREFECT_WORKER_IMAGE@$PREFECT_WORKER_IMAGE@g" \
    -e "s/WORK_POOL_NAME/$PREFECT_WORK_POOL_NAME/g" \
    -e "s@GIT_REPO@$GIT_REPO@g" \
    -e "s/GIT_TAG/$TAG/g" \
    $SCRIPT_DIR/prefect.yaml.in  > $PREFECT_FILE


BUILD_COMMAND="docker compose -f $COMPOSE_FILE build"

echo DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 $BUILD_COMMAND
DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 $BUILD_COMMAND
STATUS=$?
if [ $STATUS != 0 ]; then
    echo docker compose build failed: $STATUS 1>&2
    exit 1
fi

if [ "x$BUILD_ONLY" != x ]; then
    echo 'build done'
    exit 0
fi

# only needed if using multi-host swarm?
#echo docker compose push:
#docker compose push --quiet
#STATUS=$?
#if [ $STATUS != 0 ]; then
#    echo docker compose push failed: $STATUS 1>&2
#    exit 1
#fi

echo 'docker stack deploy'
echo '(Ignore message "Ignoring unsupported options: build")'
# added explicit --detach to silence complaints
# add --prune to remove old services?
docker stack deploy -c $COMPOSE_FILE --detach $STACK_NAME
STATUS=$?
if [ $STATUS != 0 ]; then
    echo docker stack deploy failed: $STATUS 1>&2
    exit 1
fi

echo "$DATE_TIME $HOSTNAME $STACK_NAME $REMOTE TAG" >> $SCRIPT_DIR/deploy.log
# XXX chown to LOGIN_USER? put in docker group??

# optionally prune old images?

echo "Reporting deployment to Airtable (best effort)"
report_deployment
