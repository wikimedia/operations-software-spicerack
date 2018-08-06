"""Top level cookbook"""


def get_title(args):
    """Calculate the title based on the args."""
    return '{doc}: {args}'.format(doc=__doc__, args=args)


def main(args, verbose, dry_run):
    """As required by spicerack."""
    print('args={args}, verbose={verbose}, dry_run={dry_run}'.format(args=args, verbose=verbose, dry_run=dry_run))
    return 0
