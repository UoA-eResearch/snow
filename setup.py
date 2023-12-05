from setuptools import setup, find_packages

setup(
    name='snow',
    version='0.1',
    packages=find_packages(),
    install_requires=[
        "requests",
        "beautifulsoup4",
        "six",
        "tabulate",
        "python-editor",
        "click",
        "html5lib"
    ],
    entry_points='''
        [console_scripts]
        snow=snow.snow:snow
    ''',
)
