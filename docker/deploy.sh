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
COMPOSE_FILE=docker-swarm.yaml	# in SCRIPT_DIR

if [ ! -f $SCRIPT_DIR/$COMPOSE_FILE ]; then
    echo cannot find $SCRIPT_DIR/$COMPOSE_FILE 1>&2
    exit 1
fi

# hostname w/o any domain
HOSTNAME=$(hostname --short)
BRANCH=$(git branch --show-current)

#if ! python3 -m mc-manage.airtable-deployment-update  --help >/dev/null; then
#    echo FATAL: deployment requires an up-to-date venv with pyairtable requirements 1>&2
#    exit 3
#fi

# capture command line
DEPLOYMENT_OPTIONS="$*"

usage() {
    # NOTE! If you change something in this function, run w/ -h
    # and put updated output into README.md file!!!
    echo "Usage: $SCRIPT [options]"
    echo "options:"
    echo "  -a      allow-dirty; no dirty/push checks; no tags applied (for dev)"
    echo "  -b      build image but do not deploy"
    echo "  -B BR   dry run for specific branch BR (ie; staging or prod, for testing)"
    echo "  -d      enable debug output (show environment variables)"
    echo "  -h      output this help and exit"
    echo "  -n      dry-run: do not deploy (implies -a)"
    exit 1
}

# if you add an option here, add to usage function above!!!
while getopts abB:dn OPT; do
   case "$OPT" in
   a) KITCHEN_ALLOW_DIRTY=1;; # allow default from environment!
   b) BUILD_ONLY=1;;
   B) NO_ACTION=1; AS_USER=1; KITCHEN_ALLOW_DIRTY=1; BRANCH=$OPTARG;;
   d) DEBUG=1;;
   n) NO_ACTION=1; AS_USER=1; KITCHEN_ALLOW_DIRTY=1;;
   ?) usage;;		# here on 'h' '?' or unhandled option
   esac
done

# XXX complain if anything extra on command line?

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

# report dirty repo
dirty() {
    if [ "x$KITCHEN_ALLOW_DIRTY" = x ]; then
	echo "$*" 1>&2
	exit 1
    fi
    echo "ignored: $*" 1>&2
    IS_DIRTY=1
}

if ! git diff --quiet; then
    dirty 'local changes not checked in' 1>&2
fi

# defaults for template variables that might change based on BRANCH/DEPLOY_TYPE
# (in alphabetical order):

KITCHEN_PORT=8000		# native port
PREFECT_PORT=4200		# native port
STATSD_REALM="$BRANCH"

# depends on proxy running on tarbell
STATSD_URL=statsd://stats.tarbell.angwin

# set DEPLOY_TIME, check remotes up to date
case "$BRANCH" in
prod|staging)
    if [ "x$KITCHEN_ALLOW_DIRTY" != x -a "x$NO_ACTION" = x ]; then
	echo "dirty option not allowed on $BRANCH branch: ignoring" 1>&2
	KITCHEN_ALLOW_DIRTY=
    fi
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
    STATSD_REALM=$LOGIN_USER
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

if [ "x$IS_DIRTY" = x ]; then
    # use git tag for image tag.
    # in development this means old tagged images will pile up until removed
    IMAGE_TAG=$(echo $TAG | sed 's/[^a-zA-Z0-9_.-]/_/g')
else
    # _could_ include DATE_TIME, but old images can be easily pruned:
    IMAGE_TAG=$LOGIN_USER-dirty
    # for use with git hash
    DIRTY=-dirty
fi

# Set most variables here
# PLEASE try to keep alphabetical to avoid duplicates/confusion!

# figure out some way to have these interpolated into .yml file
# (and appear as an attribute of the services?)
DEPLOYMENT_BRANCH=$BRANCH
DEPLOYMENT_DATE_TIME=$DATE_TIME
DEPLOYMENT_GIT_HASH=$(git rev-parse HEAD)$DIRTY
DEPLOYMENT_HOST=$HOSTNAME
DEPLOYMENT_USER=$LOGIN_USER
# also DEPLOYMENT_OPTIONS

KITCHEN_IMAGE_REPO=mcsystems # XXX local unless production??
KITCHEN_IMAGE_NAME=sc-kitchen
KITCHEN_IMAGE_TAG=latest # XXX want $TAG

KITCHEN_IMAGE=$KITCHEN_IMAGE_REPO/$KITCHEN_IMAGE_NAME:$KITCHEN_IMAGE_TAG
# calculate published port numbers using deployment-type bias:
KITCHEN_PORT_PUBLISHED=$(expr $KITCHEN_PORT + $PORT_BIAS)

# allow multiple deploys on same swarm/cluster:
NETWORK_NAME=$STACK_NAME

# calculate published port numbers using deployment-type bias:
PREFECT_PORT_PUBLISHED=$(expr $PREFECT_PORT + $PORT_BIAS)
PREFECT_URL=http://$PREFECT_SERVER:$PREFECT_PORT/api
# might vary if using a shared prefect server?
PREFECT_WORK_POOL_NAME=kitchen-work-pool

# Add new variables above this line,
# PLEASE try to keep alphabetical to avoid duplicates/confusion!

# some commands require compose.yml in the current working directory:
cd $SCRIPT_DIR

PRIVATE_CONF_DIR=private-conf$$
# clean up on exit unless debugging
if [ "x$DEBUG" = x ]; then
    trap "rm -f $CONFIG $COMPOSE; rm -rf $PRIVATE_CONF_DIR " 0
fi

zzz() {
    echo $1 | tr 'A-Za-z' 'N-ZA-Mn-za-m'
}

case $DEPLOY_TYPE in
prod|staging|dev)		# TEMP! include dev!!!
    rm -rf $PRIVATE_CONF_DIR
    run_as_login_user mkdir $PRIVATE_CONF_DIR
    chmod go-rwx $PRIVATE_CONF_DIR
    cd $PRIVATE_CONF_DIR
    CONFIG_REPO_PREFIX=$(zzz tvg@tvguho.pbz:zrqvnpybhq)
    CONFIG_REPO_NAME=$(zzz fbhf-purs-pbasvt)
    echo cloning $CONFIG_REPO_NAME repo 1>&2
    if ! run_as_login_user "git clone $CONFIG_REPO_PREFIX/$CONFIG_REPO_NAME.git" >/dev/null 2>&1; then
	echo "FATAL: could not clone config repo" 1>&2
	exit 1
    fi
    PRIVATE_CONF_REPO=$(pwd)/$CONFIG_REPO_NAME
    PRIVATE_CONF_FILE=$PRIVATE_CONF_REPO/.env
    cd ..
    ;;
dev)
    # NOTE! in SCRIPT_DIR!
    PRIVATE_CONF_FILE=./${LOGIN_USER}.env
    ;;
esac

# diaplay things that vary by stack type, from most to least interesting
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

# NOTE! COULD pass DEPLOY_TYPE, but would rather
# pass multiple variables that effect specific outcomes
# (keep decision making in this file, and not template;
#  don't ifdef C code based on platform name, but on features)

# PLEASE keep in alphabetical order to avoid duplicates

# experiment and see if can be subbed into 
exp DEPLOYMENT_BRANCH		# for context
exp DEPLOYMENT_DATE_TIME	# for context
exp DEPLOYMENT_GIT_HASH		# for context
exp DEPLOYMENT_HOST		# for context
exp DEPLOYMENT_USER		# for context

exp KITCHEN_IMAGE
exp KITCHEN_PORT int
exp KITCHEN_PORT_PUBLISHED int

exp NETWORK_NAME

exp PREFECT_CONTAINERS
exp PREFECT_PORT int
exp PREFECT_PORT_PUBLISHED int
exp PREFECT_SERVER		# container name
exp PREFECT_URL
exp PREFECT_WORK_POOL_NAME	# used multiple places

exp PRIVATE_CONF_FILE

exp STACK_NAME
#exp STATSD_REALM
#exp STATSD_URL

# add new variables in alphabetical order ABOVE!

echo "testing $COMPOSE_FILE" 1>&2
DUMPFILE=$COMPOSE_FILE.$TAG
rm -f $DUMPFILE
#strace -f docker stack config -c $COMPOSE_FILE > $DUMPFILE
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
else
    # maybe only keep if $DEBUG set??
    echo "output (with variables interpolated) in $DUMPFILE" 1>&2
fi

# XXX check if on suitable server (right swarm?) for prod/staging??

if [ "x$NO_ACTION" != x ]; then
    echo 'dry run: quitting' 1>&2
    exit 0
fi

if [ "x$IS_DIRTY" = x ]; then
    # XXX display all commits not currently deployed?
    # use docker image tag running on stack as base??
    echo "Last commit:"
    git log -n1
else
    echo "dirty repo"
fi

if [ "x$BUILD_ONLY" = x ]; then
    echo ''
    echo -n "Deploy from branch $BRANCH stack $STACK_NAME? [no] "
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
if [ "x$IS_DIRTY" = x ]; then
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
fi


echo compose build:
docker compose build
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
# added explicit --detach to silence complaints
# add --prune to remove old services?
docker stack deploy -c $COMPOSE_FILE --detach $STACK_NAME
STATUS=$?
if [ $STATUS != 0 ]; then
    echo docker stack deploy failed: $STATUS 1>&2
    exit 1
fi

echo deployed stack $STACK

# keep (private) record of deploys:
if [ "x$IS_DIRTY" = x ]; then
    NOTE="$REMOTE $TAG"
else
    NOTE="(dirty)"
fi
echo "$DATE_TIME $HOSTNAME $STACK_NAME $NOTE" >> deploy.log
# XXX chown to LOGIN_USER?

# optionally prune old images?

# report deployment to airtable
#export AIRTABLE_API_KEY
#export MEAG_BASE_ID
#if [ "x$AIRTABLE_API_KEY" != x ]; then
#    python3 -m mc-manage.airtable-deployment-update --codebase "story-indexer" --name $STACK_NAME --env $DEPLOYMENT_TYPE --version $IMAGE_TAG --hardware $HOSTNAME
#fi
