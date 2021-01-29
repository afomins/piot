#!/bin/bash

PIOT="/home/afomins/git/piot/scripts/piot2.py"
SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"
SENSOR_RANDOM="--random"
SERVER_PROTO="http"
SERVER_ADDR="localhost"
SERVER_PORT="8000"
SERVER_AUTH_TOKEN="qwerty"

while [ 1 ]; do
    if [ 1 -eq 0 ]; then
    echo "  Reading sensor :: type=ds18b20 id=$SENSOR_ID"
    out=`$PIOT --action=read-sensor-ds18b20 --sensor-id=$SENSOR_ID $SENSOR_RANDOM`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break

    echo "  Writing backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-write --sensor-name=$SENSOR_NAME --data=[$data]`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break
    fi

    echo "  Reading backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-read --sensor-name=$SENSOR_NAME`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break

    echo "  Sending backlog to server :: server=$SERVER_PROTO://$SERVER_ADDR:$SERVER_PORT"
    data="[{\"action\":\"backlog-write\"}]"
    out=`$PIOT --action=http-client --proto=$SERVER_PROTO --addr=$SERVER_ADDR --port=$SERVER_PORT --auth-token=$SERVER_AUTH_TOKEN --data=$data`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    error=`echo $out | jq .error`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    echo "    >> error   = $error"
    [ x$success != xtrue ] && break

    break
done
