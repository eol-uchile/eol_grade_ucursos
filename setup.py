import setuptools

setuptools.setup(
    name="gradeucursos",
    version="1.0.0",
    author="Oficina EOL UChile",
    author_email="eol-ing@uchile.cl",
    description="Allows you to transform an eol grade report to upload grades in your courses.",
    url="https://eol.uchile.cl",
    packages=setuptools.find_packages(),
    install_requires=[
        "unidecode>=1.1.1",
        "XlsxWriter>=1.3.7"
        ],
    classifiers=[
        "Programming Language :: Python :: 2",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "lms.djangoapp": ["gradeucursos = gradeucursos.apps:GradeUcursosConfig"]},
)
