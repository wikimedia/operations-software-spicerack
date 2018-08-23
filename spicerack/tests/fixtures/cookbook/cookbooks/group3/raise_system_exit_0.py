"""Group3 Raise SystemExit(0)"""
import argparse

__title__ = __doc__


def main(args, spicerack):
    """As required by spicerack.cookbook."""
    print('args={args}, verbose={verbose}, dry_run={dry_run}'.format(
        args=args, verbose=spicerack.verbose, dry_run=spicerack.dry_run))
    if args:
        parser = argparse.ArgumentParser('Raise SystemExit(0)')
        parser.parse_args(args)
    else:
        raise SystemExit(0)
