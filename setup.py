from setuptools import setup

setup(
    name="BeakerUtil",
    version="0.1.0",
    author="Abhay Deshpande",
    description="Command-line tool for beaker utilities",
    # long_description=open("README.md").read(),
    # long_description_content_type="text/markdown",
    # url="",
    py_modules=["beaker_util.main"],
    scripts=["bin/beaker_util"],
    install_requires=open("requirements.txt").read().split("\n")
)