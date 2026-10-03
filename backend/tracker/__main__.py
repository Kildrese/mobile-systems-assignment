"""`python -m tracker run [--config PATH] [--out PATH]`: one tracker run.

Exit status: 0 complete, 2 partial (a budget ran out), 3 terminal provider failure,
1 invalid policy, missing key or a locked state file.
"""

import argparse
import sys

from tracker.config import TrackerSecrets, load_policy
from tracker.errors import PolicyError, StateLocked
from tracker.loop import Runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tracker", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the tracker once")
    run.add_argument("--config", help="policy file (default: config.yaml at the repo root)")
    run.add_argument("--out", help="report path (default: reports/<run_id>.md)")
    args = parser.parse_args(argv)

    try:
        policy = load_policy(args.config)
        keys = TrackerSecrets.load(policy)
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 1

    try:
        result = Runner(policy, keys, out=args.out).run()
    except StateLocked as err:
        print(err, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "Interrupted. The run is recorded as failed; its trace is in traces/.", file=sys.stderr
        )
        return 130

    print(result.message, file=sys.stderr if result.status == "failed" else sys.stdout)
    print(f"Report: {result.report_path}")
    print(f"Trace:  {result.trace_path}")
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
