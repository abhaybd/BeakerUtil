from setuptools import setup

setup(
    name="BeakerUtil",
    version="0.1.0",
    author="Abhay Deshpande",
    description="Command-line tool for beaker utilities",
    # long_description=open("README.md").read(),
    # long_description_content_type="text/markdown",
    # url="",
    entry_points={
        "console_scripts": [
            "beakerutil = beaker_util.main:main"
        ]
    },
    py_modules=["beaker_util.main"],
    install_requires=open("requirements.txt").read().split("\n")
)
