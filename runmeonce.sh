cd "$(dirname "$0")"

source local.env
DISPLAY=:0 uv run main.py --config ${SOCO_CONFIG:-configFrontRoom.yaml} -f
echo "SOMETHING WENT WRONG.  EXIT"
