# Dart kernel for Jupyter
[Example](https://github.com/nufeng1999/jupyter-MyDart-kernel/blob/master/example/jupyter_dart_readme.ipynb "Example")
* Make sure you have the following requirements installed:
  * dart
  * jupyter
  * python 3
  * pip

### Step-by-step

```bash
git clone https://github.com/nufeng1999/jupyter-MyDart-kernel.git
cd jupyter-MyDart-kernel
pip install -e .  # for system install: sudo install .
cd jupyter_MyDart_kernel && install_MyDart_kernel --user # for sys install: sudo install_dart_kernel
# now you can start the notebook
jupyter notebook
```

## License

[MIT](LICENSE.txt)
