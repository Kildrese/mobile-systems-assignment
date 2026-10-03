"""`python -m tracker run [--config PATH] [--out PATH]`: one tracker run.

With `agents` and `use_case` in the policy, the use case's stages run under the
conductor; otherwise the single-agent tracker runs.

Exit status: 0 complete, 2 partial (a budget ran out), 3 terminal provider failure
(single agent) or failed required stage, 1 invalid policy, missing key or a locked state
file.
"""

import argparse
import sys

from tracker import conductor
from tracker.config import TrackerSecrets, load_policy, load_use_case
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
        if bool(policy.agents) != bool(policy.use_case):
            raise PolicyError("Invalid policy: agents and use_case must be set together.")
        keys = TrackerSecrets.load(policy)
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 1

    try:
        if policy.use_case:
            use_case = load_use_case(policy.use_case)
            result = conductor.run(
                policy,
                keys,
                use_case.stages(policy),
                getattr(use_case, "report_writer", None),
                out=args.out,
            )
        else:
            result = Runner(policy, keys, out=args.out).run()
    except PolicyError as err:
        print(err, file=sys.stderr)
        return 1
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
