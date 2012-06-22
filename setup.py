from setuptools import setup, find_packages

setup(
    name='json-field',
    version='0.1',
    description='A simple django json field',
    long_description=open('README.md').read(),
    author='Maxime Barbier',
    author_email='maxime.barbier1991@gmail.com',
    url='https://github.com/Krozark/django-json-field/tree/master',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        'Development Status :: 0 ',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Django',
    ],
    zip_safe=False,
)
