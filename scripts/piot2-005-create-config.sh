#!/bin/bash

# Dump dummy config to stdout; caller is responsible for saving it in file
echo "\
SENSOR_ID=\"00000000000\"
SENSOR_NAME=\"br5-bsmt-temp-heater-in\"
SENSOR_TYPE=\"temperature\"
SENSOR_RANDOM=\"--random\"

SERVER_PROTO=\"http\"
SERVER_ADDR=\"localhost\"
SERVER_PORT=\"8000\"
SERVER_AUTH_TOKEN=\"qwerty\""