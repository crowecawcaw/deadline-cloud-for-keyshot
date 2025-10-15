#!/bin/sh
# Set the -e option
set -e

hatch build
hatch run installer:build-installer $@
