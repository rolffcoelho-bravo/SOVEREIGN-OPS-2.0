"""Start the real ASGI server on loopback and verify its public G0 boundary."""

import json
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main() -> None:
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(  # noqa: S603 -- fixed local Python module, no shell
            [
                sys.executable,
                "-m",
                "uvicorn",
                "sovereign_ops.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError("ASGI server exited before liveness succeeded")
                try:
                    with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                        f"http://127.0.0.1:{port}/health/live",
                        timeout=1,
                    ) as response:
                        body = json.load(response)
                        if response.status != 200 or body != {
                            "status": "alive",
                            "stage": "G0",
                            "mode": "RESEARCH_ONLY",
                            "inference": "NOT_IMPLEMENTED",
                        }:
                            raise RuntimeError("Unexpected liveness response")
                    break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("ASGI server did not become live") from None
                    time.sleep(0.1)
            for path in ("/health/ready", "/v1/analysis"):
                try:
                    with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                        f"http://127.0.0.1:{port}{path}",
                        timeout=2,
                    ):
                        raise RuntimeError(f"Unimplemented route returned success: {path}")
                except HTTPError as error:
                    if error.code != 404:
                        raise
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "live": body,
                        "ready_http_status": 404,
                        "analysis_http_status": 404,
                        "server": "uvicorn",
                        "transport": "loopback HTTP",
                    }
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
