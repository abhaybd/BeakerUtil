from setuptools import setup, find_packages

setup(
    name="BeakerUtil",
    version="0.2.8",
    author="Abhay Deshpande",
    author_email="abhayd@allenai.org",
    description="Command-line tool for beaker utilities",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/abhaybd/BeakerUtil",
    project_urls={
        "Bug Reports": "https://github.com/abhaybd/BeakerUtil/issues",
        "Source": "https://github.com/abhaybd/BeakerUtil",
        "Documentation": "https://github.com/abhaybd/BeakerUtil#readme",
    },
    license="MIT",
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
    ],
    entry_points={
        "console_scripts": [
            "beakerutil = beaker_util.main:main",
            "beakerlaunch = beaker_util.launch_interactive:launch"
        ]
    },
    packages=find_packages(),
    install_requires=open("requirements.txt").read().split("\n")
)
