#!/bin/sh
#Run configuration steps againsts a prefect instance. 


echo "==> Running prefect-config.py"
python /app/prefect-config.py

echo "==> Running prefect deploy"
prefect --no-prompt deploy --name $SC_PREFECT_DEPLOYMENT