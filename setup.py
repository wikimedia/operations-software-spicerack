"""Package configuration."""

from setuptools import find_packages, setup

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()


INSTALL_REQUIRES = [
    "conftool>=1.0.1",
    "cumin>=3.0.2",
    "dnspython>=1.16.0,<2.2.0",  # Temporary upper limit to prevent mypy failures
    "elasticsearch>=5.0.0,<7.15.0",
    "elasticsearch-curator~=5.0",
    "gitpython>=3.1.14",
    "kafka-python>=1.4.3",
    "kubernetes==12.0.*",  # frozen to the version available on debian bullseye
    "packaging",
    "pymysql>=0.9.3",
    "pynetbox~=6.6",
    "redis>=3.2.1,<=4.1.3",
    "requests>=2.21.0",
    "wmflib",
]

# Extra dependencies
EXTRAS_REQUIRE = {
    # Test dependencies
    "tests": [
        "bandit>=1.5.1",
        "flake8>=3.6.0",
        "mypy>=0.670",
        "pytest-cov>=2.6.0",
        "pytest-xdist>=1.26.1",
        "pytest>=3.10.1",
        "requests-mock>=1.5.2",
        # This is required for flake8 to run proprely, as when running tox
        # setuptools comes boundled is usually way older (debian sid has 44 as
        # of writing this).
        "setuptools>=53.0",
        "sphinx_rtd_theme>=1.0",
        "sphinx-argparse>=0.2.2",
        "Sphinx>=1.8.4",
        "types-PyMySQL",
        "types-redis",
        "types-requests",
        "types-setuptools",
    ],
    "format": [
        "black<=21.12b0",  # this is needed so that it doesn't confict with curator
        "isort",
    ],
    "prospector": [
        "prospector[with_everything]>=0.12.4,<=1.7.7",  # Temporary upper limit for an upstream regression
        "pylint<2.15.7",  # Temporary upper limit for a change that breaks prospector that can't be upgraded
        "pytest>=3.10.1",
        "requests-mock>=1.5.2",
    ],
}

SETUP_REQUIRES = [
    "pytest-runner>=2.7.1",
    "setuptools_scm>=1.15.0",
]

setup(
    author="Riccardo Coccioli",
    author_email="rcoccioli@wikimedia.org",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX :: BSD",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Clustering",
        "Topic :: System :: Distributed Computing",
        "Topic :: System :: Systems Administration",
    ],
    description="Automation framework for the WMF production infrastructure",
    entry_points={"console_scripts": ["cookbook = spicerack._cookbook:main"]},
    extras_require=EXTRAS_REQUIRE,
    install_requires=INSTALL_REQUIRES,
    keywords=["wmf", "automation", "orchestration"],
    license="GPLv3+",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/x-rst",
    name="wikimedia-spicerack",  # Must be the same used for __version__ in __init__.py
    package_data={"spicerack": ["py.typed"]},
    packages=find_packages(exclude=["*.tests", "*.tests.*"]),
    platforms=["GNU/Linux"],
    python_requires=">=3.9",
    setup_requires=SETUP_REQUIRES,
    use_scm_version=True,
    url="https://github.com/wikimedia/operations-software-spicerack",
    zip_safe=False,
)
