#!/bin/bash

# Validate arguments
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 [SCRIPTS-DIR] [CFG-DIR]"
    exit 42
fi
S=$1; C=$2

# >>>
    # $S/piot2-100-sensor-to-db.sh $C/test-000.cfg
# <<<
