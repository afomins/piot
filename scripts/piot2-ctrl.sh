#!/bin/bash

# Vars
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
CONFIG_DIR="$SCRIPTS_DIR/cfg"
DOCKER_IMAGE_NAME="piot2"
ARGS_NO_CONTAINER=""

# Parse arguments
for i in "$@"; do
    case $i in
        --action=*)
        ARGS_ACTION="${i#*=}"
        ARGS_NO_CONTAINER+=" --action=$ARGS_ACTION"
        shift
        ;;
        --config=*)
        ARGS_CONFIG_NAME="${i#*=}"
        ARGS_NO_CONTAINER+=" --config=$ARGS_CONFIG_NAME"
        shift
        ;;
        --container)
        ARGS_IN_CONTAINER=true
        shift
        ;;
        --cmd=*)
        ARGS_CMD="${i#*=}"
        ARGS_NO_CONTAINER+=" --cmd=$ARGS_CMD"
        shift
        ;;
        *)
        ;;
    esac
done

# ------------------------------------------------------------------------------
usage () {
    echo """
Usage: $0 --action=xxx
"""
    exit 42
}

# ------------------------------------------------------------------------------
hook_write() {
    local config_name=$1
    local hook_name=$2
    local hook_path=$3

    echo "\$SCRIPTS_DIR/$hook_name \$CONFIG_DIR/$config_name" >> $hook_path
}

# ------------------------------------------------------------------------------
hook_cleanup() {
    local config_name=$1
    local hook_path=$2
    local hook_path_tmp="$hook_path.tmp"

    cat $hook_path | grep -v $config_name > $hook_path_tmp
    mv $hook_path_tmp $hook_path
}

# ------------------------------------------------------------------------------
hook_apply_config() {
    local config_path=$1
    local config_name=`basename $config_path`
    local onCloseConfig=""
    local clientHookPath="$HOOKS_DIR/piot2-client-hook.sh"
    local serverHookPath="$HOOKS_DIR/piot2-server-hook.sh"

    # Intro
    echo "Applying hooks for config:"
    cat $path

    # Remove old hooks
    hook_cleanup $config_name $clientHookPath
    hook_cleanup $config_name $serverHookPath

    # Read config file and apply hooks
    while IFS= read -r line
    do
        # Hooks are located in comments that's why we ignore non-commented lines
        [[ ! $line =~ ^#.* ]] && continue

        # Remove whitespaces and comments for easy splitting
        line=`echo "$line" | tr -d " " | tr -d "/#"`

        # Split line into "event:hook:enabled" tokens
        IFS=':' read -r -a tokens <<< "$line"
        [ "${#tokens[@]}" -ne 3 ] && continue
        local event="${tokens[0]}"
        local hook="${tokens[1]}"
        local enabled="${tokens[2]}"

        # Ignore disabled hooks
        [ "$enabled" != "yes" ] && continue

        # OnCloseConfig
        [ "$event" == "OnCloseConfig" ] && \
            onCloseConfig=$event

        # OnClientHook
        [ "$event" == "OnClientHook" ] && \
            hook_write "$config_name" "$hook" "$clientHookPath"

        # OnServerHook
        [ "$event" == "OnServerHook" ] && \
            hook_write "$config_name" "$hook" "$serverHookPath"

    done < "$config_path"
}

# ------------------------------------------------------------------------------
create_config() {
    local path=$1
    local open_editor=$2

    if [ -n "$open_editor" ]; then
        # Create dummy config if it's missing
        [ ! -f "$path" ] && echo '''# Config
SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"
SENSOR_TYPE="temperature"
SENSOR_RANDOM="--random"

SERVER_PROTO="http"
SERVER_ADDR="localhost"
SERVER_PORT="8000"
SERVER_AUTH_TOKEN="qwerty"

# Hooks:
#     OnCloseConfig:piot2-create-sensor-in-db.sh    : yes
#
#     OnClientHook:piot2-write-sensor-to-db.sh      : yes
#     OnClientHook:piot2-write-sensor-to-backlog.sh : no
#     OnClientHook:piot2-send-backlog-to-server.sh  : no
        ''' > $path

        # Open config file for editing
        nano $path
    fi

    # Apply new config
    hook_apply_config $path
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
sensors_enable() {
echo '''# ds18b20 temperature sensor
w1-gpio
w1-therm
''' > /etc/modules-load.d/piot2-sensors.conf
    [ $? -eq 0 ] && echo "Successfully added startup modules" \
        || echo "Failed to add startup modules"
    modprobe w1-gpio && echo "Successfully loaded w1-gpio" \
        || echo "Failed to load w1-gpio"
    modprobe w1-therm && echo "Successfully loaded w1-therm" \
        || echo "Failed to load w1-therm"
}

# ------------------------------------------------------------------------------
sensors_disable() {
    modprobe -r w1-therm && echo "Successfully unloaded w1-therm" \
        || echo "Failed to unload w1-therm"
    modprobe -r w1-gpio && echo "Successfully unloaded w1-gpio" \
        || echo "Failed to unload w1-gpio"
    rm /etc/modules-load.d/piot2-sensors.conf
    [ $? -eq 0 ] && echo "Successfully removed startup modules" \
        || echo "Failed to remove startup modules"
}

# ------------------------------------------------------------------------------
server_start() {
    echo "Starting piot2 server"
    /opt/piot2/piot2-start-server.sh /opt/piot2/cfg/server.cfg
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
    ''' > $dest
}

# ------------------------------------------------------------------------------
container_start() {
    local name=$1
    local dockerfile=$2
    local rc=0

    # Create image if it's absent
    (podman image exists $name) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo "Creating docker file :: path=$dockerfile"
        create_docker_file $dockerfile

        echo "Creating image :: name=$name"
        podman build -f $dockerfile -t $name

        echo "Creating container"
        podman create --name $name \
            --volume /etc/localtime:/etc/localtime:ro \
            --volume /home/$(whoami)/piot/sharing:/mnt \
            --volume /sys/fs/cgroup:/sys/fs/cgroup:ro \
            --tmpfs /tmp --tmpfs /run --tmpfs /run/lock \
            $name:latest
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
    local name=$1

    echo "Stopping container :: name=$name"
    podman stop $name
}

# ------------------------------------------------------------------------------
container_delete() {
    local name=$1

    echo "Deleting image :: name=$name"
    podman stop $name
    podman rm $name
    podman rmi --force $name
}

# ------------------------------------------------------------------------------
container_status() {
    local name=$1
    podman ps -all --filter name=$name
}

# ------------------------------------------------------------------------------
container_shell() {
    local name=$1
    local cmd=$2

    [ -z "$cmd" ] && cmd="/bin/bash" # Run bash by default
    eval podman exec --interactive --tty "$name" "$cmd"
}

# ------------------------------------------------------------------------------
main() {
    local name=$DOCKER_IMAGE_NAME
    local action=$ARGS_ACTION
    local cmd=$ARGS_CMD
    local config=$ARGS_CONFIG_NAME

    # Rus action in container
    if [ -n "$ARGS_IN_CONTAINER" ]; then
        container_shell "$name" "piot2-ctrl $ARGS_NO_CONTAINER"
        exit $?
    fi

    # Run action locally
    case $action in
        hook-client)
            source $HOOKS_DIR/piot2-client-hook.sh
        ;;

        hook-server)
            source $HOOKS_DIR/piot2-server-hook.sh
        ;;

        config-create)
            path="/dev/stdout"
            if [ -n "$config" ]; then
                path="$CONFIG_DIR/$config"
                open_editor=yes

                [ ! -d "$CONFIG_DIR" ] \
                    && echo "Failed to create config :: target dir is mising" \
                    && exit 42
            fi
            create_config $path $open_editor
        ;;

        status-client)
            status_client
        ;;

        status-server)
            status_server
        ;;

        sensors-enable)
            sensors_enable
        ;;

        sensors-disable)
            sensors_disable
        ;;

        server-start)
            server_start
        ;;

        container-start)
            dockerfile="/tmp/dockerfile.$name"
            container_start "$name" "$dockerfile"
        ;;

        container-stop)
            container_stop "$name"
        ;;

        container-delete)
            container_delete "$name"
        ;;

        container-status)
            container_status "$name"
        ;;

        container-shell)
            container_shell "$name" "$cmd"
        ;;

        *)
            usage
        ;;
    esac
}
main
