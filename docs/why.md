# Motivation and vision

## Motivation

The `conda activate` and `conda deactivate` subcommands were inspired by the `virtualenv` workflow, which implied `source`-ing a shell script shipped in the virtual environment directory. Initially implemented as `source activate` and `source deactivate`, these subcommands were promoted to the `conda` command namespace in [version 4.4.0](https://github.com/conda/conda/blob/main/CHANGELOG.md#440-2017-12-20).

The 4.4.0 activation workflow is still used in `conda` (as of 25.1) and it goes a long way to provide the possibility of modifying the shell session in place. `conda activate` will modify `PATH`, inject a few environment variables and run some activation scripts. Then, `conda deactivate` needs to undo this. That's a lot of work (and code to maintain), specially considering we can accomplish the same thing in an easier way by starting a new shell with the needed modifications and then discarding the process once done. No cleanup necessary!

However, that's not all. In order to provide in-process shell state updates, the `conda` Python entry point needs to be wrapped by a `conda` shell function that intercepts the subcommands and dispatches to either shell subcommands or regular Python subcommands. _Installing_ that shell function cannot be handled by regular Python packaging operations, so a block of code is injected in your shell profile (or platform equivalent). This is what `conda` calls "initialize your shell", as provided in `conda init`.

The `conda` shell function wrapper and the initialization logic have a non-negligible maintenance cost, add testing burden, obfuscate the application model, and, more importantly, complicate the end-user installation in a very invasive way: the shell startup profile needs a block of code to define the `conda` shell function and auto-activation mechanisms. This has a non-negligible cost every time you start a login shell and leaves residual information on uninstalls.

## Vision

This project is inspired by the workflows implemented in `poetry shell` and `pixi shell`. These workflows prove that no shell initialization logic is needed for effective virtual environment management.

The idea is to start new shell processes and then run the activation logic inside them. Once done, the user exits the process and returns to the parent session. No changes to shell startup files are needed.

In POSIX shells, conda-spawn defines a `conda()` function that forwards commands to the conda executable that launched the shell. This replaces any conda function loaded by a startup file, so commands still work after activation clears `CONDA_EXE`. The function only forwards commands. It does not activate or deactivate environments in the running shell. Use `exit` or Ctrl+D to return to the parent session.

For now, this idea is distributed as an optional plugin. If proven successful and it's well received by the community, we would propose adding it as a default `conda` plugin and suggest deprecating the old workflow (`conda init`, `activate` and `deactivate`).

## References

- [`poetry shell` plugin](https://github.com/python-poetry/poetry-plugin-shell)
- [conda deep dives: `conda init` and `conda activate`](https://docs.conda.io/projects/conda/en/24.11.x/dev-guide/deep-dives/activation.html)
