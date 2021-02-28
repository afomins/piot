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

# Main
function main {
    # Create DB if it's missing
    if [ ! -f "$PATH_DATA_DB" ]; then
        prepare_action "Creating DB :: path=$PATH_DATA_DB"
        out=`$PATH_PIOT --action=db-create \
                        --db-path=$PATH_DATA_DB \
                        --auth-token=$SERVER_AUTH_TOKEN`
        process_action "$out" $?
    fi

    # Create sensor
    prepare_action "Creating sensor in DB :: path=$PATH_DATA_DB"
    out=`$PATH_PIOT --action=db-sensor-create \
                    --db-path=$PATH_DATA_DB \
                    --auth-token=$SERVER_AUTH_TOKEN \
                    --sensor-name=$SENSOR_NAME \
                    --sensor-type=$SENSOR_TYPE`
    process_action "$out" $?
}
main
