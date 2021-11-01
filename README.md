# Dart kernel for Jupyter

* Make sure you have the following requirements installed:
  * dart
  * jupyter
  * python 3
  * pip

### Step-by-step

```bash
git clone https://github.com/nufeng1999/jupyter-dart-kernel.git
cd jupyter-dart-kernel
pip install -e .  # for system install: sudo install .
cd jupyter_dart_kernel && install_dart_kernel --user # for sys install: sudo install_dart_kernel
# now you can start the notebook
jupyter notebook
```

## License

[MIT](LICENSE.txt)
