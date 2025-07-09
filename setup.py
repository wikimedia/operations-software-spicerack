"""Package configuration."""

from setuptools import find_packages, setup

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()


INSTALL_REQUIRES = [
    "conftool>=5.0.0",
    "cumin>=3.0.2",
    "dnspython~=2.0.0; python_version=='3.9'",
    "dnspython~=2.3.0; python_version>'3.9'",
    "elasticsearch>=5.0.0,<7.15.0; python_version=='3.9'",
    "gitpython>=3.1.14",
    "kafka-python~=2.0.1",
    "kubernetes==12.0.*; python_version=='3.9'",  # frozen to the version available on debian bullseye
    "kubernetes==22.6.*; python_version>'3.9'",  # frozen to the version available on debian bookworm
    "packaging",
    "pymysql>=0.9.3",
    "pynetbox~=7.4",
    "python-etcd~=0.4.5",
    "redis>=3.5.3,<=4.1.3; python_version=='3.9'",
    "redis==4.3.*; python_version>'3.9'",
    "requests>=2.25.0",
    "wmflib",
]

# Extra dependencies
EXTRAS_REQUIRE = {
    # Test dependencies
    "tests": [
        "bandit>=1.6.2",
        "mypy>=0.812",
        "pytest-cov>=2.10.1",
        "pytest-xdist>=2.2.0",
        "pytest>=6.0.2",
        "requests-mock>=1.7.0",
        # This is required for flake8 to run proprely, as when running tox
        # setuptools comes boundled is usually way older (debian sid has 44 as
        # of writing this).
        "setuptools>=53.0",
        "sphinx_rtd_theme>=1.0",
        "sphinx-argparse>=0.2.5",
        "sphinx-autodoc-typehints>=1.9.0",
        "Sphinx>=3.4.3",
        "types-PyMySQL",
        "types-redis",
        "types-requests",
        "types-setuptools",
    ],
    "flake8": [
        "flake8>=3.8.4",
    ],
    "format": [
        "black",
        "isort",
    ],
    "prospector": [
        "prospector[with_everything]==1.15.3",  # Pinned
        "pytest>=6.0.2",
        "requests-mock>=1.7.0",
    ],
}

SETUP_REQUIRES = [
    "pytest-runner>=2.11.1",
    "setuptools_scm>=5.0.1",
]

setup(
    author="Riccardo Coccioli",
    author_email="rcoccioli@wikimedia.org",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: POSIX :: BSD",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
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
