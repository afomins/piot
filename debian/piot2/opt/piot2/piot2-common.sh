#!/bin/bash

# Validate arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 [CONFIG-PATH] [BACKLOG-NAME]"
    exit 42
fi
ARGS_CONFIG_PATH=$1
ARGS_BACKLOG_NAME=$2

# Paths
PATH_CONFIG=$ARGS_CONFIG_PATH
PATH_DATA=`dirname $PATH_CONFIG`
PATH_DATA_BACKLOG="$PATH_DATA/backlog-$ARGS_BACKLOG_NAME"
PATH_DATA_DB="$PATH_DATA/piot.sqlite"

# Load config
source $PATH_CONFIG

# Define common functions
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

__header=`printf '>%.0s' {1..80}`
function prepare_action {
    local description=$1
    echo "$__header"
    echo "  $description"
}

__piot_data=""
function process_action {
    local out=$1
    local rc=$2
    local success=$(json_read_key "$out" "success" "false")
    local error=$(json_read_key "$out" "error" "null")

    # Save "out" in global variable
    __piot_data=$(json_read_key "$out" "out" "{}")

    # Log generic parameters
    log_param "success" "$success"
    [ $rc -ne 0 ] &&
      log_param "rc" "$rc"
    log_param "error" "$error"
    log_param "data" "$__piot_data"

    # Early exit if failed
    [ "x$success" != "xtrue" ] && exit 42
}

# Show config
prepare_action "Starting piot2 wrapper ::\

    >> PATH_CONFIG=$PATH_CONFIG
    >> PATH_DATA=$PATH_DATA
    >> PATH_DATA_BACKLOG=$PATH_DATA_BACKLOG
    >> PATH_DATA_DB=$PATH_DATA_DB
    >> PATH_SCRIPTS=$PATH_SCRIPTS
    >> PATH_PIOT=$PATH_PIOT
    >> "
cat $PATH_CONFIG | awk '{print "    >> " $0}'
