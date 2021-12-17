#!/bin/bash
set -euo pipefail

if [ -f /run/secrets/metadane_deploy_token ]; then
   pip install git+https://"$(cat /run/secrets/metadane_deploy_token)"@gitlab.com/m-trader/metamodel.git
else
    pip install git+https://"$METADANE_DEPLOY_TOKEN"@gitlab.com/m-trader/metamodel.git
fi
