"""Package configuration."""

from setuptools import find_packages, setup

with open("README.rst", "r") as readme:
    LONG_DESCRIPTION = readme.read()


INSTALL_REQUIRES = [
    "conftool>=6.0.0",
    "cumin>=3.0.2",
    "dnspython~=2.3.0",
    "gitpython>=3.1.30",
    "kafka-python~=2.0.2",
    "kubernetes==22.6.*",  # frozen to the version available on debian bookworm
    "packaging",
    "pymysql>=1.0.2",
    "pynetbox~=7.4",
    "python-etcd~=0.4.5",
    "redis==4.3.*",
    "requests>=2.28.1",
    "wmflib",
]

# Extra dependencies
EXTRAS_REQUIRE = {
    # Test dependencies
    "tests": [
        "bandit>=1.6.2",
        "mypy>=1.0.1",
        "pytest-cov>=4.0.0",
        "pytest-xdist>=3.1.0",
        "pytest>=7.2.1",
        "requests-mock>=1.9.3",
        # This is required for flake8 to run proprely, as when running tox
        # setuptools comes boundled is usually way older (debian sid has 44 as
        # of writing this).
        "setuptools>=66.1.1",
        "sphinx_rtd_theme>=1.2.0",
        "sphinx-argparse>=0.3.2",
        "sphinx-autodoc-typehints>=1.12.0",
        "Sphinx>=3.4.3",
        "Sphinx>=5.3.0,<9.0.0",
        "types-PyMySQL",
        "types-redis",
        "types-requests",
        "types-setuptools",
    ],
    "flake8": [
        "flake8>=5.0.4",
    ],
    "format": [
        "black",
        "isort",
    ],
    "prospector": [
        "prospector[with_everything]==1.15.3",  # Pinned
        "pytest>=7.2.1",
        "requests-mock>=1.9.3",
    ],
}

SETUP_REQUIRES = [
    "pytest-runner>=2.11.1",
    "setuptools_scm>=7.1.0",
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
    python_requires=">=3.11",
    setup_requires=SETUP_REQUIRES,
    use_scm_version=True,
    url="https://github.com/wikimedia/operations-software-spicerack",
    zip_safe=False,
)
