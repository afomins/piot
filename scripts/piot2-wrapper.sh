#!/bin/bash

PIOT="/home/afomins/git/piot/scripts/piot2.py"
SENSOR_ID="00000000000"
SENSOR_NAME="br5-bsmt-temp-heater-in"


while [ 1 ]; do
    out=`$PIOT --action=read-sensor-ds18b20 --sensor-id=$SENSOR_ID --random`
    [ x`echo $out | jq .success` != xtrue ] && break

    data=`echo $out | jq -c .out`
    out=`$PIOT --action=backlog-write --sensor-name=$SENSOR_NAME --data=$data`
    break
done
