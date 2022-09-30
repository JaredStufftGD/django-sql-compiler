from setuptools import setup, find_packages


setup(
    name='django-sql-compiler',
    version='0.2.3',
    description="A light-weight module to generate usable SQL from a Django QuerySet.",
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Grok Data / Jared Stufft',
    author_email='jared@grokdata.tech',
    url='https://github.com/GrokData/django-sql-compiler',
    license='MIT',
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Django",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    install_requires=[
        'django',
    ],
    include_package_data=True,
    zip_safe=False,
)
