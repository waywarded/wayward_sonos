cd "$(dirname "$0")"

source local.env
DISPLAY=:0 uv run main.py --config configFrontRoom.yaml
echo "SOMETHING WENT WRONG.  EXIT"
