#!/bin/bash

# Vars
CONFIG_VERSION="1"
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
HOOK_CLIENT="$HOOKS_DIR/piot2-client-hook.sh"
HOOK_SERVER="$HOOKS_DIR/piot2-server-hook.sh"
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
# PRIVATE METHODS
# ------------------------------------------------------------------------------
_usage () {
    echo """
Usage: $0 --action=xxx
"""
    exit 42
}

_systemd_get_unit_status() {
    local unit=$1
    local value=$2
    systemctl show -p $value --value $unit
}

_systemd_analyze_timetamp() {
    local ts=$1
    systemd-analyze timestamp "$ts" | grep "From now" | awk -F: '{print $2}' | xargs
}

_hook_create_if_missing() {
    [ ! -f "$HOOK_CLIENT" ] && touch $HOOK_CLIENT
    [ ! -f "$HOOK_SERVER" ] && touch $HOOK_SERVER
}

_hook_write() {
    local config_name=$1
    local hook_name=$2
    local hook_path=$3

    echo "\$SCRIPTS_DIR/$hook_name \$CONFIG_DIR/$config_name" >> $hook_path
}

_hook_cleanup() {
    local config_name=$1
    local hook_path=$2
    local hook_path_tmp="$hook_path.tmp"

    cat $hook_path | grep -v $config_name > $hook_path_tmp
    mv $hook_path_tmp $hook_path
}

_hook_client_apply() {
    local config_path=$1
    local config_name=`basename $config_path`

    # Remove old hooks
    _hook_cleanup $config_name $HOOK_CLIENT

    # Apply hooks from config
    source $config_path
    if [ "$SERVER_ENABLED" == "true" ]; then
        # In server deployment client does following:
        #  * Saves sensor data to local backlog
        #  * Tries sending local backlog to remote server
        echo "Applying client hooks for server deployment:"
        _hook_write "$config_name" "piot2-write-sensor-to-backlog.sh" "$HOOK_CLIENT"
        _hook_write "$config_name" "piot2-send-backlog-to-server.sh" "$HOOK_CLIENT"
    else
        # In serverless deployment client writes sensor data directly fo DB
        echo "Applying client hooks for serverless deployment:"
        _hook_write "$config_name" "piot2-write-sensor-to-db.sh" "$HOOK_CLIENT"
    fi
    cat $HOOK_CLIENT
}

_hook_server_apply() {
    local config_path=$1
    local config_name=`basename $config_path`

    # Remove old hooks
    _hook_cleanup $config_name $HOOK_SERVER

    # Apply hooks from config
    echo "Applying server hooks"
    _hook_write "$config_name" "piot2-write-sensor-to-db.sh" "$HOOK_SERVER"
    cat $HOOK_SERVER
}

_container_test() {
    (which podman) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo """Error: podman is missing! 
  Install podman by running following shell command -> 
    sudo apt-get update && sudo apt-get install podman

  Or follow installation instructions here -> 
    https://podman.io/getting-started/installation"""
        exit 42
    fi
}

_create_docker_file() {
    local dest=$1

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
    ''' > $dest
}

# ------------------------------------------------------------------------------
# PUBLIC METHODS
# ------------------------------------------------------------------------------
hook_server_start() {
    echo "Starting piot2 server"
    /opt/piot2/piot2-start-server.sh /opt/piot2/cfg/server.cfg
}

config_create() {
    local mode=$1
    local path=$2

    # Create dummy config
    if [ "$path" == "/dev/stdout" ] || [ ! -f "$path" ]; then
        # Common header
        echo """# Config created @ $(date)
CONFIG_VERSION=\"$CONFIG_VERSION\"""" > $path

        # Client-only stuff
        [ "$mode" == "client" ] && echo """
SENSOR_ID=\"00000000000\"
SENSOR_NAME=\"br5-bsmt-temp-heater-in\"
SENSOR_TYPE=\"temperature\"
SENSOR_RANDOM=\"--random\"""" >> $path

        # Common stuff
        echo """
SERVER_ENABLED=\"false\"
SERVER_PROTO=\"http\"
SERVER_ADDR=\"localhost\"
SERVER_PORT=\"8000\"
SERVER_AUTH_TOKEN=\"qwerty\"""" >> $path
    fi

    # Open dummy config for editing
    if [ "$path" != "/dev/stdout" ]; then
         nano $path

        # Show final config after editing
        cat $path && echo

        # Apply hooks from config
        [ "$mode" == "client" ] && \
            _hook_client_apply $path || \
            _hook_server_apply $path
    fi
}

status_show() {
    local json="{\"hooks\":{}, \"http-server\":{}, \"config\":{}}"

    # Hooks
    for hook_name in client server; do
        # State of the timer
        local unit="piot2-$hook_name-hook.timer"
        local state_active=$(_systemd_get_unit_status $unit "ActiveState")
        local state_sub=$(_systemd_get_unit_status $unit "SubState")
        json=$(echo $json | jq -Mc ".hooks.$hook_name.timer.state = \"$state_active:$state_sub\"")

        if [ "$state_active" == "active" ]; then
            # Activity of the timer
            local ts_activated=$(_systemd_get_unit_status $unit "ActiveEnterTimestamp")
            local ts_prev_call=$(_systemd_get_unit_status $unit "LastTriggerUSec")
            local ts_next_call=$(_systemd_get_unit_status $unit "NextElapseUSecRealtime")
            local diff_activated=$(_systemd_analyze_timetamp "$ts_activated")
            local diff_prev_call=$(_systemd_analyze_timetamp "$ts_prev_call")
            local diff_next_call=$(_systemd_analyze_timetamp "$ts_next_call")
            json=$(echo $json | jq -Mc ".hooks.$hook_name.timer.\"activated\" = \"$ts_activated:$diff_activated\"")
            json=$(echo $json | jq -Mc ".hooks.$hook_name.timer.\"prev-call\" = \"$ts_prev_call:$diff_prev_call\"")
            json=$(echo $json | jq -Mc ".hooks.$hook_name.timer.\"next-call\" = \"$ts_next_call:$diff_next_call\"")

            # State of the unit
            unit="piot2-$hook_name-hook"
            state_active=$(_systemd_get_unit_status $unit "ActiveState")
            state_sub=$(_systemd_get_unit_status $unit "SubState")
            json=$(echo $json | jq -Mc ".hooks.$hook_name.unit.state = \"$state_active:$state_sub\"")

            local ts_exit=$(_systemd_get_unit_status $unit "ExecMainExitTimestamp")
            local diff_exit=$(_systemd_analyze_timetamp "$ts_exit")
            json=$(echo $json | jq -Mc ".hooks.$hook_name.unit.\"exit\" = \"$ts_exit:$diff_exit\"")
        fi
    done

    # Http server
    local unit="piot2-server.timer"
    local state_active=$(_systemd_get_unit_status $unit "ActiveState")
    local state_sub=$(_systemd_get_unit_status $unit "SubState")
    json=$(echo $json | jq -Mc ".\"http-server\".state = \"$state_active:$state_sub\"")

    # Configs
    for cfg_path in $CONFIG_DIR/*.cfg; do
        cfg_name=$(basename $cfg_path)
        cfg_name_masked="\"$cfg_name\""
        json=$(echo $json | jq -Mc ".config.$cfg_name_masked = {}")

        # Walk hooks files
        for hook_name in client-hook server-hook; do
            [ "$hook_name" == "client-hook" ] && hook_path=$HOOK_CLIENT \
                                              || hook_path=$HOOK_SERVER
            hook_name="\"$hook_name\""
            json=$(echo $json| jq -Mc ".config.$cfg_name_masked.$hook_name = []")

            # Search for config being used in hook files
            while IFS= read -r line; do
                # Trim whitespaces
                line=$(echo $line | xargs)

                # Parse line in hook file. 
                # Example:
                #     $SCRIPTS_DIR/piot2-write-backlog-to-db.sh $CONFIG_DIR/server.cfg
                #     $SCRIPTS_DIR/piot2-write-sensor-to-db.sh $CONFIG_DIR/test-000.cfg 
                IFS='/ ' read l_script_dir l_script l_cfg_dir l_cfg << EOF
                $line
EOF
#                echo "DBG: cfg_name=$cfg_name, l_script_dir=$l_script_dir, l_script=$l_script, l_cfg_dir=$l_cfg_dir, l_cfg=$l_cfg"

                # Validate format of the hook
                [ "$l_script_dir" != '$SCRIPTS_DIR' ] || [ "$l_cfg_dir" != '$CONFIG_DIR' ] && \
                    continue

                # Ignore foreign configs
                [ "$l_cfg" != "$cfg_name" ] && continue

                # Append script to the list of the hooks
                json=$(echo $json| jq -Mc ".config.$cfg_name_masked.$hook_name += [\"$l_script\"]")
            done < "$hook_path"
        done
    done
    echo $json | jq
}

client_enable() {
    echo "Enabling piot client service"
    systemctl enable piot2-client-hook
    systemctl enable piot2-client-hook.timer

    systemctl start piot2-client-hook
    systemctl start piot2-client-hook.timer
}

client_disable() {
    echo "Disabling piot client service"
    systemctl stop piot2-client-hook
    systemctl stop piot2-client-hook.timer

    systemctl disable piot2-client-hook
    systemctl disable piot2-client-hook.timer
}

server_enable() {
    echo "Enabling piot server service"
    systemctl enable piot2-server
    systemctl enable piot2-server-hook
    systemctl enable piot2-server-hook.timer

    systemctl start piot2-server
    systemctl start piot2-server-hook
    systemctl start piot2-server-hook.timer
}

server_disable() {
    echo "Disabling piot server service"
    systemctl stop piot2-server
    systemctl stop piot2-server-hook
    systemctl stop piot2-server-hook.timer

    systemctl disable piot2-server
    systemctl disable piot2-server-hook
    systemctl disable piot2-server-hook.timer
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

package_install() {
    echo "Downloading latest piot2 package"
    # curl https://bla-bla-bla

    echo "Installing latest piot2 package"
    sudo apt --yes install ./piot2_0.1.0_all.deb
}

container_start() {
    local name=$1
    local dockerfile=$2
    local rc=0

    # Create image if it's absent
    (podman image exists $name) &> /dev/null; rc=$?
    if [ $rc -ne 0 ]; then
        echo "Creating docker file :: path=$dockerfile"
        _create_docker_file $dockerfile

        echo "Creating image :: name=$name"
        podman build -f $dockerfile -t $name

        sharing_path="/home/$(whoami)/piot/sharing"
        mkdir -p $sharing_path

        echo "Creating container with shared dir=$sharing_path"
        podman create --name $name \
            --volume /etc/localtime:/etc/localtime:ro \
            --volume $sharing_path:/mnt \
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

container_stop() {
    local name=$1

    echo "Stopping container :: name=$name"
    podman stop $name
}

container_delete() {
    local name=$1

    echo "Deleting image :: name=$name"
    podman stop $name
    podman rm $name
    podman rmi --force $name
}

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

# ------------------------------------------------------------------------------
# MAIN
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
        # ----------------------------------------------------------------------
        # HOOKS
        hook-client)
            _hook_create_if_missing
            source $HOOK_CLIENT
        ;;

        hook-server)
            _hook_create_if_missing
            source $HOOK_SERVER
        ;;

        hook-server-start)
            hook_server_start
        ;;

        # ----------------------------------------------------------------------
        # CONFIG
        config-*-create)
            _hook_create_if_missing

            # Validate config destination
            path="/dev/stdout"
            if [ -n "$config" ]; then
                path="$CONFIG_DIR/$config"

                [ ! -d "$CONFIG_DIR" ] \
                    && echo "Failed to create config :: target dir is mising" \
                    && exit 42
            fi

            # Client config
            if [ "$action" == "config-client-create" ]; then
                config_create "client" "$path"

            # Server config
            elif [ "$action" == "config-server-create" ]; then
                config_create "server" "$path"

            # Unknown
            else
                _usage
            fi
        ;;

        # ----------------------------------------------------------------------
        # CLIENT
        client-enable)
            client_enable
        ;;

        client-disable)
            client_disable
        ;;

        # ----------------------------------------------------------------------
        # SERVER
        server-enable)
            server_enable
        ;;

        server-disable)
            server_disable
        ;;

        # ----------------------------------------------------------------------
        # SENSORS
        sensors-enable)
            sensors_enable
        ;;

        sensors-disable)
            sensors_disable
        ;;

        # ----------------------------------------------------------------------
        # PACKAGE
        package-install)
            package_install
        ;;

        # ----------------------------------------------------------------------
        # CONTAINER
        container-start)
            dockerfile="/tmp/dockerfile.$name"
            _container_test
            container_start "$name" "$dockerfile"
        ;;

        container-stop)
            _container_test
            container_stop "$name"
        ;;

        container-delete)
            _container_test
            container_delete "$name"
        ;;

        container-status)
            _container_test
            container_status "$name"
        ;;

        container-shell)
            _container_test
            container_shell "$name" "$cmd"
        ;;

        *)
            _hook_create_if_missing
            status_show
        ;;
    esac
}
main
