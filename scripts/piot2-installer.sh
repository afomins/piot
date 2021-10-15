#!/bin/bash

# Vars
DIR_SCRIPTS="/opt/piot2"
DIR_HOOKS="$DIR_SCRIPTS/hooks"
CONTAINER_PIOT2="piot2"
CONTAINER_GRAFANA="piot2-grafana"

# Parse arguments
ARGS_ACTION="status"
ARGS_DEB_PATH=`(ls piot2*.deb 2> /dev/null || echo darn...piot2-deb-not-found) | head -n1`
ARGS_CONTAINER_NAME="piot2"
for i in "$@"; do
    case $i in
        --action=*)
        ARGS_ACTION="${i#*=}"
        shift
        ;;
        --deb-path=*)
        ARGS_DEB_PATH="${i#*=}"
        shift
        ;;
        --container=*)
        ARGS_CONTAINER_NAME="${i#*=}"
        shift
        ;;
        *)
        ;;
    esac
done

# ------------------------------------------------------------------------------
# PRIVATE METHODS
# ------------------------------------------------------------------------------
_usage () {
    echo """
Usage: $0 --action=xxx
"""
    exit 42
}

_is_installed() {
    [[ -d "$DIR_HOOKS" ]]
}

_container_test() {
    (which podman) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo """Error: podman is missing! 
  https://podman.io/getting-started/installation"""
        exit 42
    fi
}

_container_piot2_create() {
    local name="$CONTAINER_PIOT2"
    local dockerfile="/tmp/$name.dockerfile"
    local rc=0

    # Return if images exists
    (podman image exists $name) &> /dev/null; rc=$?
    [ $rc -eq 0 ] && return

    # Create dockerfile
    echo '''FROM ubuntu:20.04

ENV container docker
ENV LC_ALL C
ENV DEBIAN_FRONTEND noninteractive

RUN sed -i "s/# deb/deb/g" /etc/apt/sources.list

RUN apt-get update \
    && apt-get install -y systemd systemd-sysv python3 jq sqlite3 nano \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN cd /lib/systemd/system/sysinit.target.wants/ \
    && ls | grep -v systemd-tmpfiles-setup | xargs rm -f $1

RUN rm -f /lib/systemd/system/multi-user.target.wants/* \
    /etc/systemd/system/*.wants/* \
    /lib/systemd/system/local-fs.target.wants/* \
    /lib/systemd/system/sockets.target.wants/*udev* \
    /lib/systemd/system/sockets.target.wants/*initctl* \
    /lib/systemd/system/basic.target.wants/* \
    /lib/systemd/system/anaconda.target.wants/* \
    /lib/systemd/system/plymouth* \
    /lib/systemd/system/systemd-update-utmp*

VOLUME [ "/sys/fs/cgroup" ]

CMD ["/lib/systemd/systemd"]
    ''' > $dockerfile

    echo "Building image :: name=$name"
    podman build -f $dockerfile -t $name

    echo "Creating container in $PWD"
    mkdir -p ./mnt
    mkdir -p ./data
    podman create --name $name \
        --volume /etc/localtime:/etc/localtime:ro \
        --volume ./mnt:/mnt \
        --volume ./data:/opt/piot2 \
        --volume /sys/fs/cgroup:/sys/fs/cgroup:ro \
        --tmpfs /tmp --tmpfs /run --tmpfs /run/lock \
        $name:latest
}

# ------------------------------------------------------------------------------
# PUBLIC METHODS
# ------------------------------------------------------------------------------
container_status() {
    local name=$1
    podman ps -all --filter name=$name
}

container_shell() {
    local name=$1
    local cmd=$2

    [ -z "$cmd" ] && cmd="/bin/bash" # Run bash by default
    eval podman exec --interactive --tty "$name" "$cmd"
}

container_start() {
    local name=$1
    local rc=0

    (podman ps --filter name=$name --filter status=running | grep $name) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo "Starting container :: name=$name"
        podman start $name
    else
        echo "Container is already running :: name=$name"
    fi
    podman ps --filter name=$name
}

status_show() {
    local json="{}"

    local tmp=`_is_installed && echo true || echo false`
    json=$(echo $json | jq -Mc ".\"piot2-deployed\" = $tmp")

    tmp=`podman container exists $CONTAINER_PIOT2 &> /dev/null && echo true || echo false`
    json=$(echo $json | jq -Mc ".\"container-$CONTAINER_PIOT2\" = $tmp")

    tmp=`podman container exists $CONTAINER_GRAFANA &> /dev/null && echo true || echo false`
    json=$(echo $json | jq -Mc ".\"container-$CONTAINER_GRAFANA\" = $tmp")

    json=$(echo $json | jq -Mc ".\"deb-path\" = \"$ARGS_DEB_PATH\"")

    # Dump
    echo $json | jq
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    local action=$ARGS_ACTION
    local container=$ARGS_CONTAINER_NAME

    # Run action locally
    case $action in
        container-shell)
            _container_test
            container_shell "$container"
        ;;

        container-status)
            _container_test
            container_status "$container"
        ;;

        container-start)
            _container_test
            [ "$container" == "$CONTAINER_PIOT2" ] && \
                _container_piot2_create || \
                _container_grafana_create

            container_start "$container"
        ;;

        # ----------------------------------------------------------------------
        # STATUS
        *|status)
            status_show
        ;;
    esac
}
main
