#!/bin/bash

# Validate arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 [CONFIG-PATH]"
    exit 42
fi

# Include common scripts
PATH_SCRIPTS=`dirname "$(readlink -f "$0")"`
PATH_PIOT="$PATH_SCRIPTS/piot2.py"
source $PATH_SCRIPTS/piot2-common.sh "$1" "server"

# Main
function main {
    # Start HTTP server
    prepare_action "Starting server :: addr=$SERVER_PROTO://$SERVER_ADDR:$SERVER_PORT
    
    "

    eval "$PATH_PIOT --action=http-server \
                     --addr=$SERVER_ADDR \
                     --port=$SERVER_PORT \
                     --backlog-path=$PATH_DATA_BACKLOG \
                     --db-path=$PATH_DATA_DB"
    process_action "$out" $?
}
main
