#!/bin/bash
set -e

# Cleanup working directory
WORKING=".working"
rm -rf $WORKING

# Move data to working directory
PIOT_DIR="$WORKING/opt/piot2"
mkdir -p $PIOT_DIR
cp ./scripts/* $PIOT_DIR
cp -r ./hooks $PIOT_DIR
cp -r ./cfg $PIOT_DIR
cp -r ./DEBIAN $WORKING

# Prepare output directory
OUTPUT=".output"
mkdir -p $OUTPUT

# Put "piot2-ctrl" to /usr/bin
dh_link opt/piot2/piot2-ctrl.sh usr/bin/piot2-ctrl

# Made deb package
dpkg-deb --build $WORKING
version=$(cat DEBIAN/control | grep Version | cut -d: -f2 | xargs)
mv $WORKING.deb ./$OUTPUT/piot2-v$version.deb
