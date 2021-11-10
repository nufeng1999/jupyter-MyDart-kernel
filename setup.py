from setuptools import setup

setup(name='jupyter_MyDart_kernel',
      version='0.0.1',
      description='Minimalistic Dart kernel for Jupyter',
      author='nufeng',
      author_email='18478162@qq.com',
      license='MIT',
      classifiers=[
          'License :: OSI Approved :: MIT License',
      ],
      url='https://github.com/nufeng1999/jupyter-MyDart-kernel/',
      download_url='https://github.com/nufeng1999/jupyter-MyDart-kernel/tarball/0.0.1',
      packages=['jupyter_MyDart_kernel'],
      scripts=['jupyter_MyDart_kernel/install_MyDart_kernel'],
      keywords=['jupyter', 'notebook', 'kernel', 'dart'],
      include_package_data=True
      )
