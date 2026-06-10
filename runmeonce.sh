cd "$(dirname "$0")"

source local.env
DISPLAY=:0 uv run main.py --config ${SOCO_CONFIG:-configFrontRoom.yaml} ${SOCO_FLAGS--f}
echo "SOMETHING WENT WRONG.  EXIT"
