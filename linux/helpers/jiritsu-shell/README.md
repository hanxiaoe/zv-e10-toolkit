# Temporary root loader

Original ARM Linux code, MIT licensed under the repository LICENSE. `launch.S` and `build.py` reproduce the 440-byte camera-tested ELF. No Sony code is included. Build offline with `python -B build.py` and clang; a mismatch stops before writing output. `launch.so` SHA-256: `c22deba2d43a6643c628a0dd5e7f524fa7b50dcc766fcee0eb37d667895c4b24`.

It forks and execs `/bin/sh /tmp/jiritsu/run.sh`; it does not install a boot service. See [Jiritsu documentation](../../docs/jiritsu.md) for required temporary uploads and cleanup/power removal.
