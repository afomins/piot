#!/bin/bash

PIOT="/home/afomins/git/piot/scripts/piot2.py"
SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"
SENSOR_RANDOM="--random"
SERVER_PROTO="http"
SERVER_ADDR="localhost"
SERVER_PORT="8000"
SERVER_AUTH_TOKEN="qwerty"
ACTION_HEADER=`printf '>%.0s' {1..80}`

piot_data=""

function json_read_key {
    local json=$1
    local key=$2
    local default_value=$3
    local value="$(echo $json | jq -c .\"$key\")"
    [ $? -ne 0 ] && value=$default_value
    [ "x$value" == "xnull" ] && value=$default_value
    echo $value
}

function log_param {
    local name=$1
    local value=$2
    local limit=100

    # Ignore empty values
    [ "x$value" == "xnull" ] && return

    # Truncate value
    [ ${#value} -gt $limit ] && suffix=" ...<truncated>\n" || suffix="\n"
    printf "    >> %-15s = %.*s $suffix" "$name" $limit "$value"
}

function prepare_action {
    local description=$1
    echo "$ACTION_HEADER"
    echo "  $description"
}

function process_action {
    local out=$1
    local rc=$2
    local success=$(json_read_key "$out" "success" "false")
    local error=$(json_read_key "$out" "error" "null")

    # Save "out" in global variable
    piot_data=$(json_read_key "$out" "out" "{}")

    # Log generic parameters
    log_param "success" "$success"
    [ $rc -ne 0 ] &&
      log_param "rc" "$rc"
    log_param "error" "$error"
    log_param "data" "$piot_data"

    # Early exit if failed
    [ "x$success" != "xtrue" ] && exit 42
}

function main {
    # Read sensor
    prepare_action "Reading sensor :: type=ds18b20 id=$SENSOR_ID"
    out=`$PIOT --action=read-sensor-ds18b20 --sensor-id=$SENSOR_ID $SENSOR_RANDOM`
    process_action "$out" $?

    # Write sensor value to backlog
    prepare_action "Writing backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-write --sensor-name=$SENSOR_NAME --data=[$piot_data]`
    process_action "$out" $?

    # Read full backlog
    prepare_action "Reading backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-read --sensor-name=$SENSOR_NAME`
    process_action "$out" $?
    backlog_data=$(json_read_key "$piot_data" "data" "[]")
    backlog_size=$(json_read_key "$piot_data" "size" 0)
    time_cur=$(json_read_key "$piot_data" "time-cur" 0)
    time_first=$(json_read_key "$piot_data" "time-first" 0)
    time_last=$(json_read_key "$piot_data" "time-last" 0)
    log_param "age-first" "$(($time_cur - $time_first))"
    log_param "age-last" "$(($time_cur - $time_last))"
    log_param "backlog-size" "$backlog_size"

    # Send "backlog-write" request to server
    prepare_action "Sending backlog to server :: addr=$SERVER_PROTO://$SERVER_ADDR:$SERVER_PORT"
    data="{\"action\":\"backlog-write\", \
           \"sensor-name\":\"$SENSOR_NAME\", \
           \"data\":$backlog_data}"
    out=`$PIOT --action=http-client --proto=$SERVER_PROTO \
                                    --addr=$SERVER_ADDR \
                                    --port=$SERVER_PORT \
                                    --auth-token=$SERVER_AUTH_TOKEN \
                                    --data="$data"`
    process_action "$out" $?

    # Verify whether "backlog-write" succeeded on server
    prepare_action "Checking whether backlog was successfully written on server"
    process_action "$piot_data" $?

    # Clear local backlog after successfully uploading it to server
    prepare_action "Clearing local backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-clear --sensor-name=$SENSOR_NAME`
    process_action "$out" $?
}

# Ready, steady ..... GO!!!!!!!!!111
main
