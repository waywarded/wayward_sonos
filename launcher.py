#!/usr/bin/env python3
# Starts the app detached from the terminal (so it survives leaving SSH), restarts it after a crash,
# and refuses to start a second copy.
#   python3 launcher.py start | stop | restart | status | run   [--config configKitchen.yaml]
# Settings come from local.env (SOCO_CONFIG, SOCO_FLAGS, DISPLAY), same as the runme scripts;
# --config overrides SOCO_CONFIG for this run only.
# Standard library only, so it runs with the system python3 before uv has set anything up.
import argparse
import fcntl
import os
import shlex
import signal
import subprocess
import sys
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_PATH = os.path.join(APP_DIR, 'logs', 'launcher.lock')
LOG_PATH = os.path.join(APP_DIR, 'logs', 'run.log')
RESTART_DELAY = 10
STOP_TIMEOUT = 10
APP_ALREADY_RUNNING = 3     # main.py's ALREADY_RUNNING_EXIT_CODE

child = None
stopping = False


def loadEnv():
    env = {}
    path = os.path.join(APP_DIR, 'local.env')
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip().strip('"\'')
    return env


def configFor(env, configOverride):
    return configOverride or env.get('SOCO_CONFIG') or 'configFrontRoom.yaml'


def appCommand(env, configOverride):
    # like runmeonce.sh: fullscreen unless local.env sets SOCO_FLAGS (empty means no flags)
    flags = shlex.split(env['SOCO_FLAGS']) if 'SOCO_FLAGS' in env else ['-f']
    return ['uv', 'run', 'main.py', '--config', configFor(env, configOverride)] + flags


def appEnvironment(env):
    procEnv = dict(os.environ)
    if sys.platform.startswith('linux'):
        # from SSH there's no display set (or an X-forwarding one); the app belongs on the Pi's screen
        procEnv['DISPLAY'] = env.get('DISPLAY', ':0')
    return procEnv


# the lock is held for as long as the launcher runs; the OS drops it when the process dies,
# even after a crash or power cut, so a leftover file never blocks a start
def tryLock():
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


# the running launcher writes its pid and its --config (empty when it follows local.env) into the lock file
def runningInfo():
    fd = tryLock()
    if fd is not None:
        os.close(fd)
        return None, None
    try:
        with open(LOCK_PATH) as f:
            lines = f.read().split('\n')
        return int(lines[0]), (lines[1] if len(lines) > 1 else '') or None
    except (OSError, ValueError):
        return -1, None   # locked, but not written yet


def runningPid():
    return runningInfo()[0]


def onStopSignal(signum, frame):
    global stopping
    stopping = True
    if child is not None and child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def run(configOverride=None):
    global child
    fd = tryLock()
    if fd is None:
        print(f'already running (pid {runningPid()})')
        return 1
    os.ftruncate(fd, 0)
    os.write(fd, f'{os.getpid()}\n{configOverride or ""}'.encode())

    signal.signal(signal.SIGTERM, onStopSignal)
    signal.signal(signal.SIGINT, onStopSignal)
    os.chdir(APP_DIR)

    while not stopping:
        # re-read each time, so an edited local.env takes effect on the next restart
        env = loadEnv()
        command = appCommand(env, configOverride)
        log(f'starting: {" ".join(command)}')
        # own process group, so stop reaches uv and the python it starts
        child = subprocess.Popen(command, env=appEnvironment(env), start_new_session=True)
        code = child.wait()
        child = None
        if stopping:
            log('stopped')
            break
        if code == 0:
            log('app quit')     # press-and-hold quit: stay quit
            break
        if code == APP_ALREADY_RUNNING:
            log('another copy of the app is already running, not starting')
            break
        log(f'app exited with code {code}, restarting in {RESTART_DELAY} seconds')
        for _ in range(RESTART_DELAY * 10):
            if stopping:
                break
            time.sleep(0.1)
    return 0


def start(configOverride=None):
    pid = runningPid()
    if pid is not None:
        print(f'already running (pid {pid})')
        return 1
    if configOverride and not os.path.exists(os.path.join(APP_DIR, configOverride)):
        print(f'no such config: {configOverride}')
        return 1
    command = [sys.executable, os.path.abspath(__file__), 'run']
    if configOverride:
        command += ['--config', configOverride]
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'a') as logFile:
        # new session: not tied to this terminal, so logging out of SSH doesn't stop it
        subprocess.Popen(command, cwd=APP_DIR, stdin=subprocess.DEVNULL,
                         stdout=logFile, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(30):
        time.sleep(0.1)
        pid = runningPid()
        if pid not in (None, -1):
            print(f'started (pid {pid}) with {describeConfig(configOverride)}, output in logs/run.log')
            return 0
    print('failed to start, see logs/run.log')
    return 1


def stop(configOverride=None):
    pid = runningPid()
    if pid is None:
        print('not running')
        return 0
    if pid == -1:
        print('launcher is starting up, try again in a moment')
        return 1
    os.kill(pid, signal.SIGTERM)
    for _ in range(STOP_TIMEOUT * 10):
        time.sleep(0.1)
        if runningPid() is None:
            print('stopped')
            return 0
    print(f'still running after {STOP_TIMEOUT} seconds (pid {pid})')
    return 1


# without --config, restart keeps whatever config the running copy was started with
def restart(configOverride=None):
    if configOverride is None:
        configOverride = runningInfo()[1]
    return stop() or start(configOverride)


def status(configOverride=None):
    pid, runningConfig = runningInfo()
    if pid is None:
        print('not running')
    else:
        print(f'running (pid {pid}) with {describeConfig(runningConfig)}')
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, errors='replace') as f:
            lines = f.readlines()[-10:]
        if lines:
            print('--- logs/run.log')
            print(''.join(lines), end='')
    return 0


def describeConfig(configOverride):
    if configOverride:
        return f'{configOverride} (--config)'
    return f'{configFor(loadEnv(), None)} (local.env)'


def log(message):
    print(f'{time.strftime("%Y-%m-%d %H:%M:%S")} launcher: {message}', flush=True)


if __name__ == '__main__':
    commands = {'start': start, 'stop': stop, 'restart': restart, 'status': status, 'run': run}
    parser = argparse.ArgumentParser(description='Run the Sonos display detached, one copy only.')
    parser.add_argument('command', choices=commands.keys())
    parser.add_argument('--config', help='room config for this run, instead of SOCO_CONFIG in local.env')
    args = parser.parse_args()
    sys.exit(commands[args.command](args.config))
