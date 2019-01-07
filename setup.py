import setuptools

setuptools.setup(
    name = 'route53-add-ec2',
    version = '1.0.0dev',
    packages = setuptools.find_packages(),
    entry_points = {'console_scripts': [
        'route53-add-ec2 = route53addec2.__main__:main',
    ]},
    install_requires = ['boto3'],
)
