# Copyright 2019 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for the :mod:`pennylane` configuration classe :class:`Configuration`.
"""
# pylint: disable=protected-access

import contextlib
import io
import re
import sys

import pennylane as qml


def test_about():
    """
    about: Tests if the about string prints correct.
    """
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        qml.about()
    out = f.getvalue().strip()

    assert "Version:" in out
    pl_version_match = re.search(r"Version:\s+([\S]+)\n", out).group(1)
    assert qml.version().replace("-", ".") in pl_version_match
    assert "Numpy version" in out
    assert "Scipy version" in out
    assert "default.qubit" in out
    assert "default.gaussian" in out
