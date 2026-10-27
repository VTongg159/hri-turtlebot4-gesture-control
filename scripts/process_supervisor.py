"""Run a command in its own process group and stop its remaining children on exit."""

import os
import signal
import subprocess
import sys
import time


def group_exists(group_id):
    try:
        os.killpg(group_id, 0)
        return True
    except ProcessLookupError:
        return False


def stop_group(child):
    """Give ROS nodes time to publish zero velocity before escalating signals."""
    for sig, grace_period in ((signal.SIGINT, 8), (signal.SIGTERM, 3), (signal.SIGKILL, 1)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace_period
        while time.monotonic() < deadline:
            child.poll()
            if not group_exists(child.pid):
                return
            time.sleep(0.1)
    child.wait()


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: process_supervisor.py COMMAND [ARG ...]")

    child = subprocess.Popen(sys.argv[1:], start_new_session=True)

    def terminate(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        return child.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        stop_group(child)


if __name__ == "__main__":
    sys.exit(main())
