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
    # Read sensor value
    prepare_action "Reading ds18b20 sensor :: id=$SENSOR_ID"
    out=`$PATH_PIOT --action=read-sensor-ds18b20 \
                    --sensor-id=$SENSOR_ID $SENSOR_RANDOM`
    process_action "$out" $?

    # Write value to DB
    prepare_action "Writing DB :: name=$SENSOR_NAME"
    out=`$PATH_PIOT --action=db-sensor-write \
                    --db-path=$PATH_DATA_DB \
                    --auth-token=$SERVER_AUTH_TOKEN \
                    --sensor-name=$SENSOR_NAME \
                    --data=[$__piot_data]`
    process_action "$out" $?
    db_size=$(json_read_key "$__piot_data" "size" 0)
    new_entries=$(json_read_key "$__piot_data" "new-entries" 0)
    log_param "db-size" "$db_size"
    log_param "new-entries" "$new_entries"
}
main
