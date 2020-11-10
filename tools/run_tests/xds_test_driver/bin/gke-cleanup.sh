#!/bin/sh -ux

#set -o allexport
#. .env
#set +o allexport

cd gke && skaffold delete -v info
