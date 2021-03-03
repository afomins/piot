#!/bin/bash

# Validate arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 [CONFIG-PATH]"
    exit 42
fi

# Include common script
PATH_SCRIPTS=`dirname "$(readlink -f "$0")"`
PATH_PIOT="$PATH_SCRIPTS/piot2.py"
source $PATH_SCRIPTS/piot2-common.sh "$1" "client"

# Main
function main {
    # Read sensor backlog
    prepare_action "Reading backlog :: name=$SENSOR_NAME"
    out=`$PATH_PIOT --action=backlog-read \
                    --backlog-path=$PATH_DATA_BACKLOG \
                    --sensor-name=$SENSOR_NAME`
    process_action "$out" $?
    backlog_data=$(json_read_key "$__piot_data" "data" "[]")
    backlog_size=$(json_read_key "$__piot_data" "size" 0)
    time_cur=$(json_read_key "$__piot_data" "time-cur" 0)
    time_first=$(json_read_key "$__piot_data" "time-first" 0)
    time_last=$(json_read_key "$__piot_data" "time-last" 0)
    log_param "age-first" "$(($time_cur - $time_first))"
    log_param "age-last" "$(($time_cur - $time_last))"
    log_param "backlog-size" "$backlog_size"

    # Send sensor backlog to server
    prepare_action "Sending backlog to server :: addr=$SERVER_PROTO://$SERVER_ADDR:$SERVER_PORT"
    data="{\"action\":\"backlog-write\", \
           \"sensor-name\":\"$SENSOR_NAME\", \
           \"data\":$backlog_data}"
    out=`$PATH_PIOT --action=http-client \
                    --proto=$SERVER_PROTO \
                    --addr=$SERVER_ADDR \
                    --port=$SERVER_PORT \
                    --auth-token=$SERVER_AUTH_TOKEN \
                    --data="$data"`
    process_action "$out" $?

    # Verify whether sensor backlog was successfully stored on server
    prepare_action "Checking whether backlog was successfully written on server"
    process_action "$__piot_data" $?

    # Clear local backlog after successfully uploading it to server
    prepare_action "Clearing local backlog :: name=$SENSOR_NAME"
    out=`$PATH_PIOT --action=backlog-clear \
                    --backlog-path=$PATH_DATA_BACKLOG \
                    --sensor-name=$SENSOR_NAME`
    process_action "$out" $?
}
main
