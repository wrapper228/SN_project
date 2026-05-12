import subprocess
import sys
import time


RESTART_DELAY = 5


def main() -> None:
    while True:
        process = subprocess.Popen([sys.executable, "-m", "client.app"])
        exit_code = process.wait()
        print(f"Client exited with code {exit_code}. Restarting in {RESTART_DELAY} seconds.")
        time.sleep(RESTART_DELAY)


if __name__ == "__main__":
    main()
