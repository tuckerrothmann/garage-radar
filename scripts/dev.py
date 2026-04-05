#!/usr/bin/env python3
"""Cross-platform developer entrypoint for Garage Radar."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from venv import EnvBuilder

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

WINDOWS_FALLBACK_BINARIES = {
    "node": [Path(r"C:\Program Files\nodejs\node.exe")],
    "npm": [Path(r"C:\Program Files\nodejs\npm.cmd")],
    "docker": [Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")],
}
FRONTEND_RUNTIME_CACHE_TAG = "garage-radar-frontend-runtime:local"
FRONTEND_IMAGE_TAG = "garage-radar-frontend:latest"


def venv_python() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def ensure_venv() -> Path:
    python_path = venv_python()
    if python_path.exists():
        return python_path

    print("Creating backend virtual environment...")
    EnvBuilder(with_pip=True).create(VENV)
    return python_path


def require_venv() -> Path:
    python_path = venv_python()
    if not python_path.exists():
        raise SystemExit("backend/.venv is missing. Run `python scripts/dev.py install` first.")
    return python_path


def binary_env(binary: str | None = None) -> dict[str, str]:
    env = merged_env()
    if not binary:
        return env

    binary_dir = str(Path(binary).resolve().parent)
    current_path = env.get("PATH", "")
    path_parts = current_path.split(os.pathsep) if current_path else []
    if binary_dir not in path_parts:
        env["PATH"] = os.pathsep.join([binary_dir, current_path]) if current_path else binary_dir
    return env


def _load_repo_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        loaded[key] = value
    return loaded


def merged_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = _load_repo_env()
    env.update(os.environ)
    if extra:
        env.update(extra)
    return env


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(command, cwd=cwd or ROOT, check=True, env=merged_env(env))


def run_check(
    command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=cwd or ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=merged_env(env),
    )
    output = (completed.stdout or completed.stderr or "").strip()
    return completed.returncode == 0, output


def find_binary(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path

    if os.name == "nt":
        for candidate in WINDOWS_FALLBACK_BINARIES.get(name, []):
            if candidate.exists():
                return str(candidate)

    return None


def cmd_install(args: argparse.Namespace) -> None:
    python_path = ensure_venv()
    run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python_path), "-m", "pip", "install", "-e", ".[dev]"], cwd=BACKEND)

    if args.backend_only:
        return

    npm = find_binary("npm")
    if not npm:
        print("Skipping frontend dependency install because npm is not on PATH.")
        return

    node_modules = FRONTEND / "node_modules"
    if args.force_frontend or not node_modules.exists():
        print("Installing frontend dependencies...")
        run([npm, "install"], cwd=FRONTEND, env=binary_env(npm))
    else:
        print("Frontend dependencies already installed.")


def cmd_api(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [
        str(python_path),
        "-m",
        "uvicorn",
        "garage_radar.api.main:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]
    if not args.no_reload:
        command.append("--reload")
    run(command, cwd=BACKEND)


def cmd_scheduler(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), "-m", "garage_radar.scheduler"]
    if args.run_now:
        command.extend(["--run-now", args.run_now])
    if args.log_level:
        command.extend(["--log-level", args.log_level])
    run(command, cwd=BACKEND)


def cmd_test(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), "-m", "pytest"]
    command.extend(getattr(args, "pytest_args", None) or ["backend/tests", "-q"])
    run(command, cwd=ROOT)


def cmd_lint(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), "-m", "ruff", "check"]
    command.extend(getattr(args, "ruff_args", None) or ["backend"])
    run(command, cwd=ROOT)


def cmd_migrate(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), "-m", "alembic", "-c", str(BACKEND / "alembic.ini")]
    command.extend(getattr(args, "alembic_args", None) or ["upgrade", "head"])
    run(command, cwd=ROOT)


def cmd_seed(_: argparse.Namespace) -> None:
    python_path = require_venv()
    run([str(python_path), str(ROOT / "scripts" / "bootstrap_db.py")], cwd=ROOT)


def cmd_ingest(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), str(ROOT / "scripts" / "ingest.py")]
    command.extend(getattr(args, "ingest_args", None) or [])
    run(command, cwd=ROOT)


def cmd_refresh_identity(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), str(ROOT / "scripts" / "refresh_identity.py")]
    command.extend(getattr(args, "refresh_identity_args", None) or [])
    run(command, cwd=ROOT)


def cmd_refresh_active_auctions(args: argparse.Namespace) -> None:
    python_path = require_venv()
    command = [str(python_path), str(ROOT / "scripts" / "refresh_active_auctions.py")]
    command.extend(getattr(args, "refresh_auction_args", None) or [])
    run(command, cwd=ROOT)


def cmd_frontend(args: argparse.Namespace) -> None:
    npm = find_binary("npm")
    if not npm:
        raise SystemExit("npm is not installed or not on PATH.")
    if not (FRONTEND / "node_modules").exists():
        print("Frontend dependencies are missing. Running `npm install` first...")
        run([npm, "install"], cwd=FRONTEND, env=binary_env(npm))
    run([npm, "run", args.script], cwd=FRONTEND, env=binary_env(npm))


def _read_env_value(key: str) -> str | None:
    if not ENV_FILE.exists():
        return None
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            return value
    return None


def cmd_frontend_image(args: argparse.Namespace) -> None:
    npm = find_binary("npm")
    if not npm:
        raise SystemExit("npm is not installed or not on PATH.")
    docker = find_binary("docker")
    if not docker:
        raise SystemExit("docker is not installed or not on PATH.")

    if not (FRONTEND / "node_modules").exists():
        print("Frontend dependencies are missing. Running `npm install` first...")
        run([npm, "install"], cwd=FRONTEND, env=binary_env(npm))

    print("Building frontend locally with Next.js...")
    run([npm, "run", "build"], cwd=FRONTEND, env=binary_env(npm))

    if args.use_local_runtime_cache:
        ok, _ = run_check([docker, "image", "inspect", FRONTEND_IMAGE_TAG], env=binary_env(docker))
        if ok:
            print(f"Tagging {FRONTEND_IMAGE_TAG} as {FRONTEND_RUNTIME_CACHE_TAG} for offline-friendly rebuilds...")
            run(
                [docker, "tag", FRONTEND_IMAGE_TAG, FRONTEND_RUNTIME_CACHE_TAG],
                cwd=ROOT,
                env=binary_env(docker),
            )
            runtime_image = FRONTEND_RUNTIME_CACHE_TAG
        else:
            runtime_image = None
            print("No cached frontend runtime image found; falling back to standard Docker frontend build.")
    else:
        runtime_image = None

    api_internal_url = _read_env_value("FRONTEND_DOCKER_API_URL") or "http://api:8000"
    browser_api_url = _read_env_value("FRONTEND_BROWSER_API_URL") or "http://localhost:8000"

    if runtime_image:
        dockerfile = FRONTEND / "Dockerfile.prebuilt"
        build_command = [
            docker,
            "build",
            "--build-arg",
            f"RUNTIME_IMAGE={runtime_image}",
            "--build-arg",
            f"API_INTERNAL_URL={api_internal_url}",
            "--build-arg",
            f"NEXT_PUBLIC_API_URL={browser_api_url}",
            "-t",
            FRONTEND_IMAGE_TAG,
            "-f",
            str(dockerfile),
            str(FRONTEND),
        ]
        print(f"Packaging frontend image from local build artifacts with RUNTIME_IMAGE={runtime_image}...")
    else:
        node_image = args.node_image or "node:20-alpine"
        dockerfile = FRONTEND / "Dockerfile"
        build_command = [
            docker,
            "build",
            "--build-arg",
            f"NODE_IMAGE={node_image}",
            "--build-arg",
            f"API_INTERNAL_URL={api_internal_url}",
            "--build-arg",
            f"NEXT_PUBLIC_API_URL={browser_api_url}",
            "-t",
            FRONTEND_IMAGE_TAG,
            "-f",
            str(dockerfile),
            str(FRONTEND),
        ]
        print(f"Building frontend image with NODE_IMAGE={node_image}...")
    run(build_command, cwd=ROOT, env=binary_env(docker))

    if args.restart:
        print("Restarting frontend service from the freshly built image...")
        run([docker, "compose", "up", "-d", "frontend"], cwd=ROOT, env=binary_env(docker))


def cmd_clean(_: argparse.Namespace) -> None:
    for cache_dir in ROOT.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    for cache_dir in ROOT.rglob(".pytest_cache"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    shutil.rmtree(VENV, ignore_errors=True)


def cmd_env(_: argparse.Namespace) -> None:
    if ENV_FILE.exists():
        print(".env already exists.")
        return
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print("Created .env from .env.example")


def cmd_doctor(args: argparse.Namespace) -> None:
    checks: list[tuple[str, bool, str]] = []

    checks.append((".env", ENV_FILE.exists(), str(ENV_FILE)))

    python_path = venv_python()
    checks.append(("backend venv", python_path.exists(), str(python_path)))
    if python_path.exists():
        ok, detail = run_check(
            [str(python_path), "-c", "from garage_radar.api.main import app; print(app.title)"],
            cwd=BACKEND,
        )
        checks.append(("backend app import", ok, detail or "import failed"))

        ok, detail = run_check(
            [str(python_path), "-m", "garage_radar.scheduler", "--help"],
            cwd=BACKEND,
        )
        checks.append(("scheduler entrypoint", ok, detail.splitlines()[0] if detail else "ok"))

    npm = find_binary("npm")
    checks.append(("npm", npm is not None, npm or "not on PATH"))
    if npm:
        ok, detail = run_check([npm, "--version"], cwd=FRONTEND, env=binary_env(npm))
        checks.append(("npm version", ok, detail or "unknown"))
        checks.append(
            ("frontend deps", (FRONTEND / "node_modules").exists(), str(FRONTEND / "node_modules"))
        )

    docker = find_binary("docker")
    checks.append(("docker", docker is not None, docker or "not on PATH"))
    if docker:
        ok, detail = run_check([docker, "compose", "version"], cwd=ROOT, env=binary_env(docker))
        checks.append(("docker compose", ok, detail or "compose unavailable"))
        ok, detail = run_check([docker, "info"], cwd=ROOT, env=binary_env(docker))
        checks.append(("docker daemon", ok, detail.splitlines()[0] if detail else "unavailable"))

    failed = False
    for name, ok, detail in checks:
        label = "OK" if ok else "WARN"
        print(f"[{label}] {name}: {detail}")
        failed = failed or not ok

    if args.strict and failed:
        raise SystemExit(1)


def cmd_compose(args: argparse.Namespace) -> None:
    docker = find_binary("docker")
    if not docker:
        raise SystemExit("docker is not installed or not on PATH.")
    command = [docker, "compose"]
    command.extend(getattr(args, "compose_args", None) or ["up"])
    run(command, cwd=ROOT, env=binary_env(docker))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Garage Radar developer helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Create backend venv and install deps")
    install.add_argument("--backend-only", action="store_true")
    install.add_argument("--force-frontend", action="store_true")
    install.set_defaults(func=cmd_install)

    api = subparsers.add_parser("api", help="Run the FastAPI app")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--no-reload", action="store_true")
    api.set_defaults(func=cmd_api)

    scheduler = subparsers.add_parser("scheduler", help="Run the scheduler worker")
    scheduler.add_argument("--run-now")
    scheduler.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    scheduler.set_defaults(func=cmd_scheduler)

    test = subparsers.add_parser("test", help="Run pytest")
    test.set_defaults(func=cmd_test)

    lint = subparsers.add_parser("lint", help="Run Ruff")
    lint.set_defaults(func=cmd_lint)

    migrate = subparsers.add_parser("migrate", help="Run Alembic")
    migrate.set_defaults(func=cmd_migrate)

    seed = subparsers.add_parser("seed", help="Seed canonical reference data")
    seed.set_defaults(func=cmd_seed)

    ingest = subparsers.add_parser("ingest", help="Run source ingestion")
    ingest.set_defaults(func=cmd_ingest)

    refresh_identity = subparsers.add_parser(
        "refresh-identity",
        help="Recompute make/model identity for existing DB rows",
    )
    refresh_identity.set_defaults(func=cmd_refresh_identity)

    refresh_active_auctions = subparsers.add_parser(
        "refresh-active-auctions",
        help="Re-fetch stored active auction URLs to backfill bid/countdown data",
    )
    refresh_active_auctions.set_defaults(func=cmd_refresh_active_auctions)

    frontend = subparsers.add_parser("frontend", help="Run a frontend npm script")
    frontend.add_argument("script", nargs="?", default="dev")
    frontend.set_defaults(func=cmd_frontend)

    frontend_image = subparsers.add_parser(
        "frontend-image",
        help="Build the production frontend image, optionally using the cached local runtime image as a base",
    )
    frontend_image.add_argument("--node-image")
    frontend_image.add_argument("--no-local-runtime-cache", dest="use_local_runtime_cache", action="store_false")
    frontend_image.add_argument("--no-restart", dest="restart", action="store_false")
    frontend_image.set_defaults(
        func=cmd_frontend_image,
        use_local_runtime_cache=True,
        restart=True,
    )

    clean = subparsers.add_parser("clean", help="Remove local caches and backend venv")
    clean.set_defaults(func=cmd_clean)

    env = subparsers.add_parser("env", help="Create .env from .env.example if needed")
    env.set_defaults(func=cmd_env)

    doctor = subparsers.add_parser("doctor", help="Check local prerequisites and repo wiring")
    doctor.add_argument("--strict", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    compose = subparsers.add_parser("compose", help="Pass through to docker compose")
    compose.set_defaults(func=cmd_compose)

    return parser


def normalize_passthrough_args(extra: list[str]) -> list[str]:
    if extra and extra[0] == "--":
        return extra[1:]
    return extra


def main() -> None:
    parser = build_parser()
    args, extra = parser.parse_known_args()
    passthrough_map = {
        "test": "pytest_args",
        "lint": "ruff_args",
        "migrate": "alembic_args",
        "ingest": "ingest_args",
        "refresh-identity": "refresh_identity_args",
        "refresh-active-auctions": "refresh_auction_args",
        "compose": "compose_args",
    }
    if args.command in passthrough_map:
        setattr(args, passthrough_map[args.command], normalize_passthrough_args(extra))
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args.func(args)


if __name__ == "__main__":
    main()
