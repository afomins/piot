#!/bin/sh

usage () {
    echo "Usage: $0 [client-hook|server-hook|create-config] {config-name}"
    exit 42
}

# Validate number of arguments
[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && usage

# Define variables
ARGS_ACTION=$1
ARGS_CONFIG_NAME=$2
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
CONFIG_DIR="$SCRIPTS_DIR/cfg"
CONFIG_FILE_PATH="$CONFIG_DIR/$ARGS_CONFIG_NAME"

# Run action
case $ARGS_ACTION in
    client-hook)
        source $HOOKS_DIR/piot2-client-hook.sh
    ;;

    server-hook)
        source $HOOKS_DIR/piot2-server-hook.sh
    ;;

    create-config)
        # Dump to terminal by default
        [ -z "$ARGS_CONFIG_NAME" ] && CONFIG_FILE_PATH="/dev/stdout"

        # Write config
        (echo "SENSOR_ID=\"00000000000\""
         echo "SENSOR_NAME=\"br5-bsmt-temp-heater-in\""
         echo "SENSOR_TYPE=\"temperature\""
         echo "SENSOR_RANDOM=\"--random\""
         echo ""
         echo "SERVER_PROTO=\"http\""
         echo "SERVER_ADDR=\"localhost\""
         echo "SERVER_PORT=\"8000\""
         echo "SERVER_AUTH_TOKEN=\"qwerty\"") > $CONFIG_FILE_PATH
    ;;

    *)
        usage
    ;;
esac
