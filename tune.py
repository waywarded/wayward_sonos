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
        't': ('top margin', 'text_band_padding', 'space above the title in pixels'),
        'b': ('bottom margin', 'text_band_bottom_margin', 'space below the artist in pixels'),
        'o': ('opacity', 'text_band_alpha', '0 see-through to 255 solid'),
    }),
    't': ('band tint (both screens)', {
        'l': ('lightness', 'band_tint_lightness', '0-100 how light the colour from the cover looks'),
    }),
    'c': ('clock', {
        'f': ('feather', 'clock_backing_feather', 'soft edge height in pixels, 0 for hard'),
        'm': ('margin', 'clock_backing_padding', 'space above and below the text in pixels'),
        'o': ('opacity', 'clock_backing_alpha', '0 see-through to 255 solid'),
    }),
    'd': ('night dimming', {
        's': ('start', 'dim_start', 'HH:MM, 24-hour, or off'),
        'e': ('end', 'dim_end', 'HH:MM, 24-hour, or off'),
        'l': ('level', 'dim_level', '0 none to 255 black'),
    }),
}


def isTime(key):
    return key in ('dim_start', 'dim_end')


# a time is written quoted, '00:00' or 'off'; everything else is a bare whole number
def pattern(key):
    value = r"'?(\d{1,2}:\d{2}|off)'?" if isTime(key) else r'(-?\d+)'
    return re.compile(r'^(\s*' + re.escape(key) + r':\s*)' + value, re.M)


def current(key):
    with open(CONFIG) as f:
        match = pattern(key).search(f.read())
    return match.group(2) if match else None


def setValue(key, value):
    with open(CONFIG) as f:
        text = f.read()
    if isTime(key):
        value = f"'{value}'"
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
        choice = ask("[n]ow playing, [c]lock, [t]int, [d]imming, [r]eset all to the repo's values, [q]uit: ")
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
        if len(settings) == 1:
            choice = next(iter(settings))
        else:
            choice = ask(f"{name}: " + ', '.join(f"[{k}]{label[1:]}" for k, (label, _, _) in settings.items()) + ": ")
        if choice not in settings:
            continue
        label, key, hint = settings[choice]
        value = ask(f"{name} {label} is {current(key)} ({hint}). New value: ")
        if isTime(key):
            match = re.fullmatch(r'(\d{1,2}):?(\d{2})', value)
            if value != 'off' and not (match and int(match[1]) < 24 and int(match[2]) < 60):
                print("Not changed: needs a time like 23:30, or off.")
                continue
            if match:
                value = f"{int(match[1]):02}:{match[2]}"
        elif not re.fullmatch(r'-?\d+', value):
            print("Not changed: needs a whole number.")
            continue
        # margins can go below zero, to pull the band in over the text; the rest can't
        if isTime(key):
            pass
        elif key.endswith(('alpha', 'level')):
            value = str(max(0, min(255, int(value))))
        elif key.endswith('lightness'):
            value = str(max(0, min(100, int(value))))
        elif not key.endswith(('padding', 'margin')):
            value = str(max(0, int(value)))
        if setValue(key, value):
            print(f"{key}: {value}")
            changed = True
        else:
            print(f"{key} isn't in display_config.yaml")
    if changed:
        print("Restart the app to see it. Before a git pull, [r]eset here or the pull will refuse.")


if __name__ == '__main__':
    main()
