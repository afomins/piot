#!/bin/bash

PIOT="/home/afomins/git/piot/scripts/piot2.py"
SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"
SENSOR_RANDOM="--random"

while [ 1 ]; do
    echo "  1) Reading sensor :: type=ds18b20 id=$SENSOR_ID"
    out=`$PIOT --action=read-sensor-ds18b20 --sensor-id=$SENSOR_ID $SENSOR_RANDOM`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break

    echo "  2) Writing backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-write --sensor-name=$SENSOR_NAME --data=$data`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break

    echo "  3) Reading backlog :: name=$SENSOR_NAME"
    out=`$PIOT --action=backlog-read --sensor-name=$SENSOR_NAME`; rc=$?
    data=`echo $out | jq -c .out`
    success=`echo $out | jq .success`
    echo "    >> data    = $data"
    echo "    >> success = $success:$rc"
    [ x$success != xtrue ] && break

    break
done
