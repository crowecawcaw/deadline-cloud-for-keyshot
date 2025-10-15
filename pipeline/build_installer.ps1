$ErrorActionPreference = "Stop"

hatch build
hatch run installer:build-installer @args
