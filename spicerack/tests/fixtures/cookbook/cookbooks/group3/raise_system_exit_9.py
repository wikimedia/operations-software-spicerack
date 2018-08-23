"""Group3 Raise SystemExit(9)"""
import sys

__title__ = __doc__


def main(args, spicerack):
    """As required by spicerack.cookbook."""
    print('args={args}, verbose={verbose}, dry_run={dry_run}'.format(
        args=args, verbose=spicerack.verbose, dry_run=spicerack.dry_run))
    raise sys.exit(9)
