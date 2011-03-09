# encoding: UTF-8

from setuptools import setup

long_description = ''.join(list(open('README.txt'))[3:])
print long_description

setup(
    name='texturepacker',
    version='0.4',
    description='Assemble texture packs for Minecraft',
    #long_description=long_description,
    author='Damian Cugley',
    author_email='pdc@alleged.org.uk',
    url = 'http://pdc.github.com/texturepacker/',

    install_requires=[
        'PIL>=1.1.7',
        'PyYAML>=3.0.9',
        'httplib2>=0.6.0',
    ],
    tests_require=[
        'mock>=0.7.0b4',
        'nose>=1.0.0',
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Framework :: Zope3',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Natural Language :: English',
        'Topic :: Games/Entertainment',
        'Topic :: Utilities',
    ],
    py_modules=['texturepacker'],
    scripts=['script/maketexture'],
    # The sample images & recipes are not included in a binary distribution.
)