#!/bin/bash

# Argparse
for i in "$@"; do
case $i in
    --action=*)
    ARGS_ACTION="${i#*=}"
    shift # past argument=value
    ;;
    --config=*)
    ARGS_CONFIG_NAME="${i#*=}"
    shift # past argument=value
    ;;
    --container)
    ARGS_IN_CONTAINER=true
    shift # past argument with no value
    ;;
    --cmd=*)
    ARGS_CMD="${i#*=}"
    shift # past argument=value
    ;;
    *)
          # unknown option
    ;;
esac
done

# Define variables
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
CONFIG_DIR="$SCRIPTS_DIR/cfg"
CONFIG_FILE_PATH="$CONFIG_DIR/$ARGS_CONFIG_NAME"
DOCKER_IMAGE_NAME="piot2"
DOCKER_FILE_PATH="/tmp/dockerfile.$DOCKER_IMAGE_NAME"

# ------------------------------------------------------------------------------
usage () {
    echo """
Usage: $0 --action=aaa
"""
    exit 42
}

# ------------------------------------------------------------------------------
create_config() {
    # Dump to terminal by default
    [ -z "$ARGS_CONFIG_NAME" ] && CONFIG_FILE_PATH="/dev/stdout"
echo '''SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"
SENSOR_TYPE="temperature"
SENSOR_RANDOM="--random"

SERVER_PROTO="http"
SERVER_ADDR="localhost"
SERVER_PORT="8000"
SERVER_AUTH_TOKEN="qwerty"
''' > $CONFIG_FILE_PATH
}

# ------------------------------------------------------------------------------
status_client() {
    systemctl status piot2-client.timer
    echo
    systemctl status piot2-client
}

# ------------------------------------------------------------------------------
status_server() {
    systemctl status piot2-server.timer
    echo
    systemctl status piot2-server
}

# ------------------------------------------------------------------------------
create_docker_file() {
    local dest=$1
echo '''FROM ubuntu:18.04

ENV container docker
ENV LC_ALL C
ENV DEBIAN_FRONTEND noninteractive

RUN sed -i "s/# deb/deb/g" /etc/apt/sources.list

RUN apt-get update \
    && apt-get install -y systemd systemd-sysv python3 jq sqlite3 \
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
''' > $dest
}

# ------------------------------------------------------------------------------
container_start() {
    local name=$DOCKER_IMAGE_NAME
    local rc=0

    # Create image if it's absent
    (podman image exists $name) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo "Creating docker file :: path=$DOCKER_FILE_PATH"
        create_docker_file $DOCKER_FILE_PATH

        echo "Creating image :: name=$name"
        podman build -f $DOCKER_FILE_PATH -t $name

        echo "Creatin container"
        podman create --name $name \
            --volume /etc/localtime:/etc/localtime:ro \
            --volume /home/$(whoami)/piot/sharing:/mnt \
            --volume /sys/fs/cgroup:/sys/fs/cgroup:ro \
            --tmpfs /tmp --tmpfs /run --tmpfs /run/lock \
            $DOCKER_IMAGE_NAME:latest
    fi

    # Start container if it's not running
    (podman ps --filter name=$name --filter status=running | grep $name) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo "Starting container :: name=$name"
        podman start $name
    else
        echo "Container is already running :: name=$name"
    fi
    podman ps --filter name=$name
}

# ------------------------------------------------------------------------------
container_stop() {
    local name=$DOCKER_IMAGE_NAME

    echo "Stopping container :: name=$name"
    podman stop $name
}

# ------------------------------------------------------------------------------
container_delete() {
    local name=$DOCKER_IMAGE_NAME

    echo "Deleting image :: name=$name"
    podman stop $name
    podman rm $name
    podman rmi --force $name
}

# ------------------------------------------------------------------------------
container_status() {
    local name=$DOCKER_IMAGE_NAME
    podman ps -all --filter name=$name
}

# ------------------------------------------------------------------------------
container_shell() {
    local name=$DOCKER_IMAGE_NAME
#     podman exec --interactive --tty $name /bin/bash "ls"
    podman exec --tty $name ls
}

# ------------------------------------------------------------------------------
# Main
case $ARGS_ACTION in
    hook-client)
        source $HOOKS_DIR/piot2-client-hook.sh
    ;;

    hook-server)
        source $HOOKS_DIR/piot2-server-hook.sh
    ;;

    config-create)
        create_config
    ;;

    status-client)
        status_client
    ;;

    status-server)
        status_server
    ;;

    container-start)
        container_start
    ;;

    container-stop)
        container_stop
    ;;

    container-delete)
        container_delete
    ;;

    container-status)
        container_status
    ;;

    container-shell)
        container_shell
    ;;

    *)
        usage
    ;;
esac
