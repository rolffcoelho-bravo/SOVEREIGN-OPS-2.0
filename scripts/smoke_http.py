"""Start the real ASGI server on loopback and verify its public boundary."""

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
                            "stage": "G9",
                            "mode": "RESEARCH_ONLY",
                            "inference": "NOT_IMPLEMENTED",
                        }:
                            raise RuntimeError("Unexpected liveness response")
                    break
                except (URLError, TimeoutError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError("ASGI server did not become live") from None
                    time.sleep(0.1)
            # Verify readiness probe is available
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/health/ready",
                timeout=2,
            ) as ready_response:
                ready_body = json.load(ready_response)
                if ready_response.status != 200:
                    raise RuntimeError("Readiness probe failed")

            # Verify provenance endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/provenance/registry",
                timeout=2,
            ) as prov_response:
                prov_body = json.load(prov_response)
                if prov_response.status != 200:
                    raise RuntimeError("Provenance endpoint failed")

            # Verify quality schemas endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/quality/schemas",
                timeout=2,
            ) as quality_response:
                quality_body = json.load(quality_response)
                if quality_response.status != 200:
                    raise RuntimeError("Quality schemas endpoint failed")
                if len(quality_body.get("schemas", [])) < 2:
                    raise RuntimeError("Expected at least 2 schemas")

            # Verify G3 detectors endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/models/detectors",
                timeout=2,
            ) as det_response:
                det_body = json.load(det_response)
                if det_response.status != 200:
                    raise RuntimeError("Detectors endpoint failed")
                families = det_body.get("families", [])
                if len(families) < 2:
                    raise RuntimeError("Expected at least 2 detector families")

            # Verify G3 evaluation protocol endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/models/evaluation-protocol",
                timeout=2,
            ) as eval_response:
                eval_body = json.load(eval_response)
                if eval_response.status != 200:
                    raise RuntimeError("Evaluation protocol endpoint failed")

            # Verify G4 pipeline config endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/pipeline/config",
                timeout=2,
            ) as pipe_response:
                pipe_body = json.load(pipe_response)
                if pipe_response.status != 200:
                    raise RuntimeError("Pipeline config endpoint failed")
                if pipe_body.get("stage") != "G9":
                    raise RuntimeError("Pipeline config stage != G9")

            # Verify G4 decision protocol endpoint
            with urlopen(  # noqa: S310 -- fixed loopback HTTP URL
                f"http://127.0.0.1:{port}/pipeline/decision-protocol",
                timeout=2,
            ) as dec_response:
                dec_body = json.load(dec_response)
                if dec_response.status != 200:
                    raise RuntimeError("Decision protocol endpoint failed")
                if len(dec_body.get("outcomes", [])) != 5:
                    raise RuntimeError("Expected 5 decision outcomes")

            # Verify unimplemented routes return 404
            for path in ("/v1/analysis",):
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
                        "ready": ready_body,
                        "provenance_datasets": len(prov_body.get("datasets", [])),
                        "quality_schemas": len(quality_body.get("schemas", [])),
                        "detector_families": len(families),
                        "evaluation_protocol": eval_body.get("name"),
                        "pipeline_stage": pipe_body.get("stage"),
                        "decision_outcomes": len(dec_body.get("outcomes", [])),
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
