#!/bin/bash

# Vars
PKG_NAME="piot2"
CONTAINER_PIOT2="piot2"
CONTAINER_GRAFANA="piot2-grafana"

# Parse arguments
ARGS_ACTION="fuck"
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
_echo_bool() {
    [ $? -eq 0 ] && echo true || echo false
}

_container_list() {
    local name=$1
    podman ps --all --filter name=piot2
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
    podman ps --filter name=^$name$ --filter status=running | grep $name &> /dev/null
}

_container_piot2_create() {
    local name_container="$CONTAINER_PIOT2"
    local name_image="localhost/$CONTAINER_PIOT2"
    local dockerfile="/tmp/$name.dockerfile"
    local rc=0

    # Return if container already exists
    (podman container exists $name_container) &> /dev/null; rc=$?
    [ $rc -eq 0 ] && return

    # Create image if it's missing
    (podman image exists $name_image) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
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

        echo "Creating image :: name=$name_image"
        podman build            \
            --file $dockerfile  \
            --tag $name_image
    fi

    echo "Creating container :: name=$name_container path=$PWD"
    mkdir -p ./mnt
    mkdir -p ./data/cfg
    podman create \
        --name $name_container \
        --hostname $name_container \
        --volume /etc/localtime:/etc/localtime:ro \
        --volume /sys/fs/cgroup:/sys/fs/cgroup:ro \
        --volume ./mnt:/mnt \
        --volume ./data:/opt/piot2 \
        --tmpfs /tmp \
        --tmpfs /run \
        --tmpfs /run/lock \
        $name_image
}

_container_grafana_create() {
    local name_container="$CONTAINER_GRAFANA"
    local name_image="grafana/grafana:latest-ubuntu"
    local rc=0

    # Return if images exists
    (podman container exists $name_container) &> /dev/null; rc=$?
    [ $rc -eq 0 ] && return

    echo "Creating container :: name=$name_container path=$PWD"
    podman run -d \
        -p 3000:3000 \
        --name=$name_container \
        --hostname=$name_container \
        --volume ./data/cfg:/piot2 \
        --net="host" \
        -e "GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource,frser-sqlite-datasource" \
        $name_image
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
}

container_delete() {
    local name=$1

    echo "Deleting container :: name=$name"
    podman stop $name > /dev/null 2>&1
    podman rm $name
}

container_install_deb() {
    local name=$1
    local deb_path=$2
    local deb_name=`basename $deb_path`

    echo "Installing deb in container :: name=$name deb=$deb_path"
    cp $deb_path ./mnt && \
        container_shell $ARGS_CONTAINER_NAME "dpkg -i /mnt/$deb_name"
}

sensors_enable() {
    echo "Loading sensor kernel modules"
    sudo sh -c "echo '''# ds18b20 temperature sensor
w1-gpio
w1-therm
''' > /etc/modules-load.d/piot2-sensors.conf"
    [ $? -eq 0 ] && echo "Successfully added startup modules" \
        || echo "Failed to add startup modules"
    sudo modprobe w1-gpio && echo "Successfully loaded w1-gpio" \
        || echo "Failed to load w1-gpio"
    sudo modprobe w1-therm && echo "Successfully loaded w1-therm" \
        || echo "Failed to load w1-therm"
}

sensors_disable() {
    echo "Unloading sensor kernel modules"
    sudo modprobe -r w1-therm && echo "Successfully unloaded w1-therm" \
        || echo "Failed to unload w1-therm"
    sudo modprobe -r w1-gpio && echo "Successfully unloaded w1-gpio" \
        || echo "Failed to unload w1-gpio"
    sudo rm /etc/modules-load.d/piot2-sensors.conf
    [ $? -eq 0 ] && echo "Successfully removed startup modules" \
        || echo "Failed to remove startup modules"
}

status_show() {
    local json="{}"
    local tmp=""
    local ccc=""
    local prefix=""

    # containers.piot2.is-installed
    ccc=$CONTAINER_PIOT2
    prefix=".containers.\"$ccc\""
    tmp=`podman container exists $ccc > /dev/null 2>&1; _echo_bool`
    json=$(echo $json | jq -Mc "$prefix.\"is-installed\" = $tmp")

    # containers.piot2.is-running
    tmp=`_container_is_running $ccc; _echo_bool`
    json=$(echo $json | jq -Mc "$prefix.\"is-running\" = $tmp")

    # containers.piot2.deb-version
    cmd="dpkg -S $PKG_NAME > /dev/null 2>&1 && dpkg-query --show $PKG_NAME | cut -f2 || echo null"
    tmp=`_container_is_running $ccc && \
        container_shell $ccc "$cmd" || echo null`
    [ "$tmp" != "null" ] && tmp="\"$tmp\""
    json=$(echo $json | jq -Mc "$prefix.\"deb-version\" = $tmp")

    # containers.piot2-grafana.is-installed
    ccc=$CONTAINER_GRAFANA
    prefix=".containers.\"$ccc\""
    tmp=`podman container exists $ccc > /dev/null 2>&1; _echo_bool`
    json=$(echo $json | jq -Mc "$prefix.\"is-installed\" = $tmp")

    # container.piot2-grafana.is-running
    tmp=`_container_is_running $ccc; _echo_bool`
    json=$(echo $json | jq -Mc "$prefix.\"is-running\" = $tmp")

    # sensors.w1-gpio1
    tmp=`grep -e "^w1_gpio " /proc/modules > /dev/null 2>&1; _echo_bool`
    json=$(echo $json | jq -Mc ".sensors.\"w1-gpio\" = $tmp")

    # sensors.w1-therm
    tmp=`grep -e "^w1_therm " /proc/modules > /dev/null 2>&1; _echo_bool`
    json=$(echo $json | jq -Mc ".sensors.\"w1-therm\" = $tmp")

    # Dump
    echo $json | jq
}

usage () {
    echo """
PIOT2 Installer: 
  Status:
    $0 --action=status

  Sensors:
    $0 --action=sensors-enable
    $0 --action=sensors-disable

  Container piot2:
    $0 --action=create
    $0 --action=start
    $0 --action=stop
    $0 --action=delete
    $0 --action=install-deb --deb-path=~/git/piot2_0.1.0_all.deb
    $0 --action=shell

  Container piot2-grafana:
    $0 --action=create --container=piot2-grafana 
    $0 --action=start --container=piot2-grafana
    $0 --action=stop --container=piot2-grafana
    $0 --action=delete --container=piot2-grafana
    $0 --action=shell --container=piot2-grafana
"""
    exit 42
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    local action=$ARGS_ACTION
    local container=$ARGS_CONTAINER_NAME
    local deb_path=$ARGS_DEB_PATH
    local list_running_containers=true

    # Run action
    case $action in
        shell)
            _container_test
            container_shell "$container"
            list_running_containers=false
        ;;
        create)
            _container_test
            [ "$container" == "$CONTAINER_PIOT2" ] && \
                _container_piot2_create || \
                _container_grafana_create
        ;;
        start)
            _container_test
            container_start "$container"
        ;;
        stop)
            _container_test
            container_stop "$container"
        ;;
        delete)
            _container_test
            container_delete "$container"
        ;;
        install-deb)
            _container_test
            container_install_deb "$container" "$deb_path"
        ;;
        sensors-enable)
            sensors_enable
            list_running_containers=false
        ;;
        sensors-disable)
            sensors_disable
            list_running_containers=false
        ;;
        status)
            status_show
        ;;
        *)
            usage
            list_running_containers=false
        ;;
    esac

    # List runnng containers
    [ "$list_running_containers" = true ]           \
        && echo                                     \
        && podman ps --all --filter name=piot2
}
main
