#!/bin/bash

# Vars
PKG_NAME="piot2"
DIR_SCRIPTS="/opt/piot2"
DIR_HOOKS="$DIR_SCRIPTS/hooks"
CONTAINER_PIOT2="piot2"
CONTAINER_GRAFANA="piot2-grafana"

# Parse arguments
ARGS_ACTION="status"
ARGS_DEB_PATH=`(ls piot2*.deb 2> /dev/null || echo piot2-not-found.deb) | head -n1`
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

_echo_bool() {
    [ $? -eq 0 ] && echo true || echo false
}

_is_installed() {
    [[ -d "$DIR_HOOKS" ]]
}

_container_show_status() {
    local name=$1
    podman ps -all --filter name=$name
}

_container_test() {
    (which podman) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo """Error: podman is missing! 
  https://podman.io/getting-started/installation"""
        exit 42
    fi
}

_container_is_running() {
    local name=$1
    podman ps --filter name=$name --filter status=running | grep $name &> /dev/null
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

_container_grafana_create() {
    local name="$CONTAINER_GRAFANA"
    local rc=0

    # Return if images exists
    (podman image exists $name) &> /dev/null; rc=$?
    [ $rc -eq 0 ] && return

    echo "Creating grafana container :: name=$name"
    podman run -d \
        --volume $PWD/data/cfg:/piot2 \
        --net="host" \
        --name=$name \
        -e "GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource,frser-sqlite-datasource" \
        grafana/grafana:latest-ubuntu
}

# ------------------------------------------------------------------------------
# PUBLIC METHODS
# ------------------------------------------------------------------------------
container_shell() {
    local name=$1
    local cmd=$2
    local interactive=""

    # Run interactive bash by default
    [ -z "$cmd" ]                               &&
        interactive="--interactive --tty"       && 
        cmd="/bin/bash"

    eval podman exec $interactive "$name" "bash -c '$cmd'"
}

container_start() {
    local name=$1

    _container_is_running $name
    if [ $? -ne 0 ]; then
        echo "Starting container :: name=$name"
        podman start $name
    else
        echo "Container is already running :: name=$name"
    fi
    podman ps --filter name=$name
}

container_stop() {
    local name=$1

    _container_is_running $name
    if [ $? -ne 0 ]; then
        echo "Container is not running :: name=$name"
    else
        echo "Stopping container :: name=$name"
        podman stop $name
    fi
    podman ps --filter name=$name
}

container_install_deb() {
    local name=$1
    local deb_path=$2
    local deb_name=`basename $deb_path`

    echo "Installing deb in container :: name=$name deb=$deb_path"
    cp $deb_path ./mnt && \
        container_shell $ARGS_CONTAINER_NAME "dpkg -i /mnt/$deb_name"
}

status_show() {
    local json="{}"

    # container.piot2.is-installed
    tmp=`podman container exists $CONTAINER_PIOT2 &> /dev/null; _echo_bool`
    json=$(echo $json | jq -Mc ".\"$CONTAINER_PIOT2\".\"is-installed\" = $tmp")

    # container.piot2.is-running
    tmp=`_container_is_running $CONTAINER_PIOT2; _echo_bool`
    json=$(echo $json | jq -Mc ".\"$CONTAINER_PIOT2\".\"is-running\" = $tmp")

    # container.piot2.deb-version
    cmd="dpkg -S $PKG_NAME > /dev/null 2>&1 && dpkg-query --show $PKG_NAME | cut -f2 || echo null"
    tmp=`_container_is_running $CONTAINER_PIOT2 && \
        container_shell $CONTAINER_PIOT2 "$cmd"`
    [ "$tmp" != "null" ] && tmp="\"$tmp\""
    json=$(echo $json | jq -Mc ".\"$CONTAINER_PIOT2\".\"deb-version\" = $tmp")

    # container.piot2-grafana.is-installed
    tmp=`podman container exists $CONTAINER_GRAFANA &> /dev/null; _echo_bool`
    json=$(echo $json | jq -Mc ".\"$CONTAINER_GRAFANA\".\"is-installed\" = $tmp")

    # container.piot2-grafana.is-running
    tmp=`_container_is_running $CONTAINER_GRAFANA; _echo_bool`
    json=$(echo $json | jq -Mc ".\"$CONTAINER_GRAFANA\".\"is-running\" = $tmp")

    # Dump
    echo $json | jq
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    local action=$ARGS_ACTION
    local container=$ARGS_CONTAINER_NAME
    local deb_path=$ARGS_DEB_PATH

    # Run action locally
    case $action in
        shell)
            _container_test
            container_shell "$container"
        ;;

        start)
            _container_test
            [ "$container" == "$CONTAINER_PIOT2" ] && \
                _container_piot2_create || \
                _container_grafana_create

            container_start "$container"
        ;;

        stop)
            _container_test
            container_stop "$container"
        ;;

        install-deb)
            _container_test
            container_install_deb "$container" "$deb_path"
        ;;

        *|status)
            status_show
        ;;
    esac
}
main
