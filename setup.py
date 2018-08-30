"""Package configuration."""

from setuptools import find_packages, setup

install_requires = [
    'conftool>=1.0.1',
    'cumin>=3.0.2',
    'dnspython>=1.15.0',
    'pyyaml>=3.11',
    'requests>=2.11.1',
]

# Extra dependencies
extras_require = {
    # Test dependencies
    'tests': [
        'bandit>=1.1.0',
        'flake8>=3.2.1',
        'prospector[with_everything]>=0.12.4',
        'pytest-cov>=1.8.0',
        'pytest-xdist>=1.15.0',
        'pytest>=3.0.3',
        'requests-mock>=1.3.0',
    ],
}

setup_requires = [
    'pytest-runner>=2.7.1',
    'setuptools_scm>=1.15.0',
]

setup(
    author='Riccardo Coccioli',
    author_email='rcoccioli@wikimedia.org',
    description='Automation framework for the WMF production infrastructure',
    entry_points={
        'console_scripts': [
            'cookbook = spicerack.cookbook:main',
        ],
    },
    extras_require=extras_require,
    install_requires=install_requires,
    keywords=['wmf', 'automation', 'orchestration'],
    license='GPLv3+',
    long_description="Automation and orchestration framework for the Wikimedia Foundation's production infrastructure.",
    name='wikimedia-spicerack',
    packages=find_packages(exclude=['*.tests', '*.tests.*']),
    platforms=['GNU/Linux'],
    setup_requires=setup_requires,
    use_scm_version=True,
    url='https://github.com/wikimedia/operations-software-spicerack',
    zip_safe=False,
)
