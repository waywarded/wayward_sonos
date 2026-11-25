#!/usr/bin/env python3
# Try out the band settings in display_config.yaml without an editor: pick a screen and a setting, type a value.
# Only the number on that line changes, so comments stay. Restart the app to see a change.
#   python3 tune.py
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, 'display_config.yaml')

SCREENS = {
    'n': ('now playing', {
        'f': ('feather', 'text_band_feather', 'soft edge height in pixels, 0 for hard'),
        'm': ('margin', 'text_band_padding', 'space above the title in pixels'),
        'o': ('opacity', 'text_band_alpha', '0 see-through to 255 solid'),
    }),
    'c': ('clock', {
        'f': ('feather', 'clock_backing_feather', 'soft edge height in pixels, 0 for hard'),
        'm': ('margin', 'clock_backing_padding', 'space above and below the text in pixels'),
        'o': ('opacity', 'clock_backing_alpha', '0 see-through to 255 solid'),
    }),
}


def pattern(key):
    return re.compile(r'^(\s*' + re.escape(key) + r':\s*)(-?\d+)', re.M)


def current(key):
    with open(CONFIG) as f:
        match = pattern(key).search(f.read())
    return match.group(2) if match else None


def setValue(key, value):
    with open(CONFIG) as f:
        text = f.read()
    text, count = pattern(key).subn(lambda m: m.group(1) + value, text, count=1)
    if count:
        with open(CONFIG, 'w') as f:
            f.write(text)
    return count


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return 'q'


def summary():
    for name, settings in SCREENS.values():
        values = ', '.join(f"{label} {current(key)}" for label, key, _ in settings.values())
        print(f"  {name}: {values}")


def main():
    changed = False
    while True:
        print()
        summary()
        choice = ask("[n]ow playing, [c]lock, [r]eset all to the repo's values, [q]uit: ")
        if choice == 'q':
            break
        if choice == 'r':
            subprocess.run(['git', 'checkout', '--', 'display_config.yaml'], cwd=HERE)
            print("Back to the repo's values.")
            changed = True
            continue
        if choice not in SCREENS:
            continue
        name, settings = SCREENS[choice]
        choice = ask(f"{name}: [f]eather, [m]argin, [o]pacity: ")
        if choice not in settings:
            continue
        label, key, hint = settings[choice]
        value = ask(f"{name} {label} is {current(key)} ({hint}). New value: ")
        if not re.fullmatch(r'\d+', value):
            print("Not changed: needs a whole number.")
            continue
        if key.endswith('alpha') and int(value) > 255:
            value = '255'
        if setValue(key, value):
            print(f"{key}: {value}")
            changed = True
        else:
            print(f"{key} isn't in display_config.yaml")
    if changed:
        print("Restart the app to see it. Before a git pull, [r]eset here or the pull will refuse.")


if __name__ == '__main__':
    main()
