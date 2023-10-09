"""Install packages as defined in this file into the Python environment."""
from setuptools import setup, find_namespace_packages

# The version of this tool is based on the following steps:
# https://packaging.python.org/guides/single-sourcing-package-version/
VERSION = {}

with open("./src/tsujikiri/__init__.py") as fp:
    # pylint: disable=W0122
    exec(fp.read(), VERSION)

setup(
    name="tsujikiri",
    author="kRAkEn/gORe",
    author_email="kunitoki@gmail.com",
    url="https://github.com/kunitoki/tsujikiri",
    description="辻斬り Generic C++ Bindings Generator",
    version=VERSION.get("__version__", "0.0.0"),
    python_requires=">=3",
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src", exclude=["tests"]),
    install_requires=[
        "libclang==16.0.6",
        "pyyaml==6.0.1",
    ],
    entry_points={
        "console_scripts": [
            "tsujikiri=tsujikiri.__main__:main",
        ]
    },
    classifiers=[
        "Topic :: Utilities",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3 :: Only",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
    ],
)