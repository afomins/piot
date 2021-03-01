#!/bin/bash

# Prepare working directory
WORKING=".working"
rm -rf $WORKING
mkdir -p $WORKING/opt/piot2
cp ./scripts/piot2* $WORKING/opt/piot2
cp -r ./DEBIAN $WORKING

# Prepare output directory
OUTPUT=".output"
mkdir $OUTPUT

# Run
dpkg-deb --build $WORKING
version=$(cat DEBIAN/control | grep Version | cut -d: -f2 | xargs)
mv $WORKING.deb ./$OUTPUT/piot2-v$version.deb
