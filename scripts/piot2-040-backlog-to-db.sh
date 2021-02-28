#!/bin/bash

# Validate arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 [CONFIG-PATH]"
    exit 42
fi

# Include common script
PATH_SCRIPTS=`dirname "$(readlink -f "$0")"`
PATH_PIOT="$PATH_SCRIPTS/piot2.py"
source $PATH_SCRIPTS/piot2-common.sh "$1" "server"

function main {
    # Read backlog
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

    # Write backlog to DB
    prepare_action "Writing DB :: name=$SENSOR_NAME"
    out=`$PATH_PIOT --action=db-sensor-write \
                    --db-path=$PATH_DATA_DB \
                    --auth-token=$SERVER_AUTH_TOKEN \
                    --sensor-name=$SENSOR_NAME \
                    --data=$backlog_data`
    process_action "$out" $?
    db_size=$(json_read_key "$__piot_data" "size" 0)
    new_entries=$(json_read_key "$__piot_data" "new-entries" 0)
    log_param "db-size" "$db_size"
    log_param "new-entries" "$new_entries"

    # Clear backlog after successfully writing it to db
    prepare_action "Clearing local backlog :: name=$SENSOR_NAME"
    out=`$PATH_PIOT --action=backlog-clear \
                    --backlog-path=$PATH_DATA_BACKLOG \
                    --sensor-name=$SENSOR_NAME`
    process_action "$out" $?
}
main
