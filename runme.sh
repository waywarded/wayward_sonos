cd "$(dirname "$0")"
while true; do
    source local.env
    DISPLAY=:0 uv run main.py --config ${SOCO_CONFIG:-configFrontRoom.yaml} -f
    echo "SOMETHING WENT WRONG.  RESTART IN 10 seconds"
    sleep 3
 done
