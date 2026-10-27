"""Extract official ROS simulator packages locally without changing system packages.

Package checksums come from the local apt metadata. Prefer installing the official
simulator with apt; this helper supports the local vendor fallback used on this laptop.
"""

import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
PACKAGE_LIST = Path(__file__).with_name("simulator_packages.txt")


def package_metadata(package):
    output = subprocess.check_output(["apt-cache", "show", package], text=True)
    first_version = output.split("\n\n", 1)[0]
    return dict(
        line.split(": ", 1)
        for line in first_version.splitlines()
        if ": " in line and not line.startswith(" ")
    )


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(package):
    metadata = package_metadata(package)
    destination = VENDOR_DIR / "debs" / Path(metadata["Filename"]).name
    expected = metadata["SHA256"]
    if not destination.exists() or checksum(destination) != expected:
        temporary = destination.with_suffix(".deb.part")
        url = "http://packages.ros.org/ros2/ubuntu/" + metadata["Filename"]
        subprocess.run(
            [
                "curl",
                "-4",
                "-fL",
                "--retry",
                "2",
                "--connect-timeout",
                "15",
                "--max-time",
                "120",
                "-o",
                str(temporary),
                url,
            ],
            check=True,
        )
        if checksum(temporary) != expected:
            temporary.unlink()
            raise RuntimeError(f"Package checksum mismatch: {package}")
        temporary.replace(destination)

    subprocess.run(["dpkg-deb", "-x", str(destination), str(VENDOR_DIR / "root")], check=True)
    print(f"{package}: verified and extracted", flush=True)


def main():
    (VENDOR_DIR / "debs").mkdir(parents=True, exist_ok=True)
    (VENDOR_DIR / "COLCON_IGNORE").touch()
    packages = [line.strip() for line in PACKAGE_LIST.read_text().splitlines() if line.strip()]
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(fetch, packages))


if __name__ == "__main__":
    main()
