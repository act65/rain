from setuptools import setup, find_packages

setup(
    name="rain-offchain",
    version="0.1.0",
    packages=find_packages(),
    description="Off-chain utilities for the Rain protocol.",
    author="Rain Protocol",
    author_email="",  # Add appropriate email
    url="https://github.com/rainlanguage/rain-protocol", # Replace with actual URL if different
    install_requires=[
        # Add dependencies here, e.g.,
        # "web3>=5.0.0,<6.0.0",
        # "requests>=2.0.0,<3.0.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License", # Or other appropriate license
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)
