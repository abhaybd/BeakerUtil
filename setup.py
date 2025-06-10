from setuptools import setup, find_packages

setup(
    name="BeakerUtil",
    version="0.2.0",
    author="Abhay Deshpande",
    description="Command-line tool for beaker utilities",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/abhaybd/BeakerUtil",
    entry_points={
        "console_scripts": [
            "beakerutil = beaker_util.main:main",
            "beakerlaunch = beaker_util.launch_interactive:launch"
        ]
    },
    packages=find_packages(),
    install_requires=open("requirements.txt").read().split("\n")
)
