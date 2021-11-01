from setuptools import setup

setup(name='jupyter_dart_kernel',
      version='0.0.1',
      description='Minimalistic Dart kernel for Jupyter',
      author='nufeng',
      author_email='18478162@qq.com',
      license='MIT',
      classifiers=[
          'License :: OSI Approved :: MIT License',
      ],
      url='https://github.com/nufeng1999/jupyter-dart-kernel/',
      download_url='https://github.com/nufeng1999/jupyter-dart-kernel/tarball/0.0.1',
      packages=['jupyter_dart_kernel'],
      scripts=['jupyter_dart_kernel/install_dart_kernel'],
      keywords=['jupyter', 'notebook', 'kernel', 'dart'],
      include_package_data=True
      )
