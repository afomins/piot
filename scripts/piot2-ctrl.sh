#!/bin/bash

# Vars
CONFIG_VERSION="1"
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
HOOK_CLIENT="$HOOKS_DIR/piot2-client-hook.sh"
HOOK_SERVER="$HOOKS_DIR/piot2-server-hook.sh"
CONFIG_DIR="$SCRIPTS_DIR/cfg"
DB_PATH="$CONFIG_DIR/piot.sqlite"

# Parse arguments
for i in "$@"; do
    case $i in
        --action=*)
        ARGS_ACTION="${i#*=}"
        shift
        ;;
        --config=*)
        ARGS_CONFIG_NAME="${i#*=}"
        shift
        ;;
        *)
        ;;
    esac
done

# ------------------------------------------------------------------------------
# PRIVATE METHODS
# ------------------------------------------------------------------------------
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
        _hook_write "$config_name" "piot2-write-sensor-ds18b20-to-backlog.sh" "$HOOK_CLIENT"
        _hook_write "$config_name" "piot2-send-backlog-to-server.sh" "$HOOK_CLIENT"
    else
        # In serverless deployment client writes sensor data directly fo DB
        echo "Applying client hooks for serverless deployment:"
        _hook_write "$config_name" "piot2-create-sensor-in-db.sh" "$HOOK_CLIENT"
        _hook_write "$config_name" "piot2-write-sensor-ds18b20-to-db.sh" "$HOOK_CLIENT"
    fi
}

_hook_server_apply() {
    local config_path=$1
    local config_name=`basename $config_path`

    # Remove old hooks
    _hook_cleanup $config_name $HOOK_SERVER

    # Apply hooks from config
    echo "Applying server hooks"
    _hook_write "$config_name" "piot2-write-sensor-to-db.sh" "$HOOK_SERVER"
}

_service_enable() {
    local unit=$1
    echo "Enabling piot $unit service"

    # Enable&start hooks
    systemctl enable piot2-$unit-hook
    systemctl enable piot2-$unit-hook.timer

    systemctl start piot2-$unit-hook
    systemctl start piot2-$unit-hook.timer

    # Enable&start server
    if [ "$unit" == "server" ]; then
        systemctl enable piot2-server
        systemctl start piot2-server
    fi
}

_service_disable() {
    local unit=$1
    echo "Disabling piot $unit service"

    # Disable&stop hooks
    systemctl stop piot2-$unit-hook
    systemctl stop piot2-$unit-hook.timer

    systemctl disable piot2-$unit-hook
    systemctl disable piot2-$unit-hook.timer

    # Disable&stop server
    if [ "$unit" == "server" ]; then
        systemctl stop piot2-server
        systemctl disable piot2-server
    fi
}

# ------------------------------------------------------------------------------
# PUBLIC METHODS
# ------------------------------------------------------------------------------
hook_server_start() {
    echo "Starting piot2 server"
    $SCRIPTS_DIR/piot2-start-server.sh $CONFIG_DIR/server.cfg
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
    local json="{\"app\":{}, \"hooks\":{}, \"http-server\":{}, \"config\":{}, \"db\":{}}"

    # App
    json=$(echo $json | jq -Mc ".app.version.config = \"$CONFIG_VERSION\"")

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
                IFS='/ ' read l_script_dir l_script l_cfg_dir l_cfg <<< $line
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

    # Db
    [ -f "$DB_PATH" ] && db_path="\"$DB_PATH\"" \
                      || db_path="null"
    json=$(echo $json| jq -Mc ".db.path = $db_path")

    # Dump
    echo $json | jq
}

usage () {
    echo """
PIOT2 Controller:
  Status:
    $0 --action=status

  Client:
    $0 --action=client-enable
    $0 --action=client-disable
    $0 --action=config-client-create --config=br5-bsmt-temp-heater-in

  Server:
    $0 --action=server-enable
    $0 --action=server-disable
    $0 --action=config-server-create
"""
    exit 42
}

# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------
main() {
    local action=$ARGS_ACTION
    local config=$ARGS_CONFIG_NAME

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
        config-client-create|config-server-create)
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
            status_show
        ;;

        # ----------------------------------------------------------------------
        # SERVICE UNIT STATUS
        client-enable|client-disable|server-enable|server-disable)
            IFS='-' read unit_name unit_status <<< $action
            [ "$unit_status" == "enable" ]  && _service_enable "$unit_name"
            [ "$unit_status" == "disable" ] && _service_disable "$unit_name"
        ;;

        # ----------------------------------------------------------------------
        # STUFF
        status)
            _hook_create_if_missing
            status_show
        ;;
        *)
            usage
        ;;
    esac
}
main
