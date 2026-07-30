#!/usr/bin/env python3
"""Test runner for Luminari Sage integration tests."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add src to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def run_tests(test_type="all", verbose=True):
    """Run tests with specified options."""

    # Change to project directory
    os.chdir(project_root)

    # Base pytest command
    cmd = ["python", "-m", "pytest"]

    if verbose:
        cmd.append("-v")

    # Select test type
    if test_type == "unit":
        cmd.extend(["-m", "unit"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
        cmd.extend(["--disable-warnings"])  # Integration tests may have more warnings
    elif test_type == "fast":
        cmd.extend(["-m", "not slow"])
    elif test_type == "api":
        cmd.append("tests/test_api_integration.py")
    elif test_type == "mcp":
        cmd.append("tests/test_mcp_integration.py")
    else:
        # Run all tests
        cmd.append("tests/")

    print(f"Running: {' '.join(cmd)}")
    print(f"Working directory: {os.getcwd()}")
    print("-" * 50)

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n⚠️ Tests interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error running tests ({type(e).__name__})")
        return 1


def check_services():
    """Check if required services are running."""
    import requests

    services = {"API": "http://localhost:8003/ping", "MCP": "http://localhost:8004/tools"}

    service_status = {}

    for name, url in services.items():
        try:
            response = requests.get(url, timeout=2)
            service_status[name] = response.status_code == 200
        except Exception:
            service_status[name] = False

    print("🔍 Service Status:")
    for name, status in service_status.items():
        status_emoji = "✅" if status else "❌"
        print(f"  {status_emoji} {name}: {'Running' if status else 'Not available'}")

    print()

    if not any(service_status.values()):
        print("⚠️  No services detected. Integration tests may be skipped.")
        print("💡 Start services with: docker compose up -d")
        print()

    return service_status


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run Luminari Sage tests")
    parser.add_argument(
        "type",
        nargs="?",
        default="all",
        choices=["all", "unit", "integration", "fast", "api", "mcp"],
        help="Type of tests to run",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Less verbose output")
    parser.add_argument("--no-service-check", action="store_true", help="Skip service status check")

    args = parser.parse_args()

    print("🧪 Luminari Sage Test Runner")
    print("=" * 40)

    if not args.no_service_check:
        check_services()

    # Run tests
    exit_code = run_tests(args.type, verbose=not args.quiet)

    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
