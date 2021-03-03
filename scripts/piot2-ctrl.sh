#!/bin/sh

usage () {
    echo "Usage: $0 [client-init-hook|server-init-hook|client-hook|server-hook|create-config] {config-name}"
    exit 42
}

# Validate number of arguments
[ "$#" -lt 1 ] || [ "$#" -gt 2 ] && usage

# Get destination
ACTION=$1
CONFIG_NAME=$2
SCRIPTS_DIR="/opt/piot2"
HOOKS_DIR="$SCRIPTS_DIR/hooks"
CONFIG_DIR="$SCRIPTS_DIR/cfg"
CONFIG_FILE_PATH="$CONFIG_DIR/$CONFIG_NAME"

# Run action
case $ACTION in
    client-init-hook)
        source $HOOKS_DIR/piot2-client-init-hook.sh
    ;;

    client-hook)
        source $HOOKS_DIR/piot2-client-hook.sh
    ;;

    server-init-hook)
        source $HOOKS_DIR/piot2-server-init-hook.sh
    ;;

    server-hook)
        source $HOOKS_DIR/piot2-server-hook.sh
    ;;

    create-config)
        # Dump to terminal by default
        [ -z "$CONFIG_NAME" ] && CONFIG_FILE_PATH="/dev/stdout"

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
