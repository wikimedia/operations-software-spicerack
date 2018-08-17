"""Top level cookbook"""


def get_title(args):
    """Calculate the title based on the args."""
    return '{doc}: {args}'.format(doc=__doc__, args=args)


def main(args, spicerack):
    """As required by spicerack.cookbook."""
    print('args={args}, verbose={verbose}, dry_run={dry_run}'.format(
        args=args, verbose=spicerack.verbose, dry_run=spicerack.dry_run))
    return 0
