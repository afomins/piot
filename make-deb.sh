#!/bin/bash

# Cleanup build directory
OUTPUT=".output"
rm -rf $OUTPUT
mkdir -p $OUTPUT/opt/piot2

# Prepare build directory
cp scripts/piot2* $OUTPUT/opt/piot2
cp -r DEBIAN $OUTPUT

# Run
dpkg-deb --build $OUTPUT
mc $OUTPUT.deb piot2.deb
