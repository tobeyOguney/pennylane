# Copyright 2018 Xanadu Quantum Technologies Inc.

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
This module contains utilities and auxiliary functions which are shared
across the PennyLane submodules.
"""
# pylint: disable=protected-access
from collections.abc import Iterable
from collections import OrderedDict
import numbers
import inspect
import itertools

import numpy as np

import pennylane as qml
from pennylane.variable import Variable


def _flatten(x):
    """Iterate through an arbitrarily nested structure, flattening it in depth-first order.

    See also :func:`_unflatten`.

    Args:
        x (array, Iterable, other): each element of the Iterable may itself be an iterable object

    Yields:
        other: elements of x in depth-first order
    """
    if isinstance(x, np.ndarray):
        yield from _flatten(x.flat)  # should we allow object arrays? or just "yield from x.flat"?
    elif isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
        for item in x:
            yield from _flatten(item)
    else:
        yield x


def _unflatten(flat, model):
    """Restores an arbitrary nested structure to a flattened iterable.

    See also :func:`_flatten`.

    Args:
        flat (array): 1D array of items
        model (array, Iterable, Number): model nested structure

    Raises:
        TypeError: if ``model`` contains an object of unsupported type

    Returns:
        (other, array): first elements of flat arranged into the nested
        structure of model, unused elements of flat
    """
    if isinstance(model, (numbers.Number, Variable, str)):
        return flat[0], flat[1:]
    elif isinstance(model, np.ndarray):
        idx = model.size
        res = np.array(flat)[:idx].reshape(model.shape)
        return res, flat[idx:]
    elif isinstance(model, Iterable):
        res = []
        for x in model:
            val, flat = _unflatten(flat, x)
            res.append(val)
        return res, flat
    else:
        raise TypeError("Unsupported type in the model: {}".format(type(model)))


def unflatten(flat, model):
    """Wrapper for :func:`_unflatten`.

    Args:
        flat (array): 1D array of items
        model (array, Iterable, Number): model nested structure

    Raises:
        ValueError: if ``flat`` has more elements than ``model``
    """
    # pylint:disable=len-as-condition
    res, tail = _unflatten(np.asarray(flat), model)
    if len(tail) != 0:
        raise ValueError("Flattened iterable has more elements than the model.")
    return res


def _inv_dict(d):
    """Reverse a dictionary mapping.

    Returns multimap where the keys are the former values,
    and values are sets of the former keys.

    Args:
        d (dict[a->b]): mapping to reverse

    Returns:
        dict[b->set[a]]: reversed mapping
    """
    ret = {}
    for k, v in d.items():
        ret.setdefault(v, set()).add(k)
    return ret


def _get_default_args(func):
    """Get the default arguments of a function.

    Args:
        func (callable): a function

    Returns:
        dict[str, tuple]: mapping from argument name to (positional idx, default value)
    """
    signature = inspect.signature(func)
    return {
        k: (idx, v.default)
        for idx, (k, v) in enumerate(signature.parameters.items())
        if v.default is not inspect.Parameter.empty
    }


def expand(U, wires, num_wires):
    r"""Expand a multi-qubit operator into a full system operator.

    Args:
        U (array): :math:`2^n \times 2^n` matrix where n = len(wires).
        wires (Sequence[int]): Target subsystems (order matters! the
            left-most Hilbert space is at index 0).

    Raises:
        ValueError: if wrong wires of the system were targeted or
            the size of the unitary is incorrect

    Returns:
        array: :math:`2^N\times 2^N` matrix. The full system operator.
    """
    if num_wires == 1:
        # total number of wires is 1, simply return the matrix
        return U

    N = num_wires
    wires = np.asarray(wires)

    if np.any(wires < 0) or np.any(wires >= N) or len(set(wires)) != len(wires):
        raise ValueError("Invalid target subsystems provided in 'wires' argument.")

    if U.shape != (2 ** len(wires), 2 ** len(wires)):
        raise ValueError("Matrix parameter must be of size (2**len(wires), 2**len(wires))")

    # generate N qubit basis states via the cartesian product
    tuples = np.array(list(itertools.product([0, 1], repeat=N)))

    # wires not acted on by the operator
    inactive_wires = list(set(range(N)) - set(wires))

    # expand U to act on the entire system
    U = np.kron(U, np.identity(2 ** len(inactive_wires)))

    # move active wires to beginning of the list of wires
    rearranged_wires = np.array(list(wires) + inactive_wires)

    # convert to computational basis
    # i.e., converting the list of basis state bit strings into
    # a list of decimal numbers that correspond to the computational
    # basis state. For example, [0, 1, 0, 1, 1] = 2^3+2^1+2^0 = 11.
    perm = np.ravel_multi_index(tuples[:, rearranged_wires].T, [2] * N)

    # permute U to take into account rearranged wires
    return U[:, perm][perm]


class Recorder:
    """Recorder class used by the :class:`~.OperationRecorder`.

    The Recorder class is a very minimal QNode, that simply
    provides a QNode context for operator queueing."""

    # pylint: disable=too-few-public-methods
    def __init__(self, old_context):
        self._old_context = old_context
        self._ops = []
        self.num_wires = 1

    def _append_op(self, op):
        """:class:`~.Operator` objects call this method
        and append themselves upon initialization."""
        self._ops.append(op)

        # this ensure the recorder does not interfere with
        # any QNode contexts
        if self._old_context:
            self._old_context._append_op(op)

    @property
    def queue(self):
        """Queue of the underlying QNode if existant, otherwise a copy of the internal operator list."""
        if self._old_context:
            return self._old_context.queue

        return self._ops.copy()

    # Spoof all attributes of the underlying QNode if there is one
    def __getattr__(self, name):
        if self._old_context:
            return self._old_context.__getattribute__(name)

        raise AttributeError("Attribute {} of Recorder mock QNode does not exist.".format(name))


class OperationRecorder:
    """A template and quantum function inspector,
    allowing easy introspection of operators that have been
    applied without requiring a QNode.

    **Example**:

    The OperationRecorder is a context manager. Executing templates
    or quantum functions stores resulting applied operators in the
    recorder, which can then be printed.

    >>> weights = qml.init.strong_ent_layers_normal(n_layers=1, n_wires=2)
    >>>
    >>> with qml.utils.OperationRecorder() as rec:
    >>>    qml.templates.layers.StronglyEntanglingLayers(*weights, wires=[0, 1])
    >>>
    >>> print(rec)
    Operations
    ==========
    Rot(-0.10832656163640327, 0.14429091013664083, -0.010835826725765343, wires=[0])
    Rot(-0.11254523669444501, 0.0947222564914006, -0.09139600968423377, wires=[1])
    CNOT(wires=[0, 1])
    CNOT(wires=[1, 0])

    Alternatively, the :attr:`~.OperationRecorder.queue` attribute can be used
    to directly accessed the applied :class:`~.Operation` and :class:`~.Observable`
    objects.

    Attributes:
        rec (~.Recorder): a very minimal QNode, that simply
            acts as a QNode context for operator queueing
        queue (List[~.Operators]): list of operators applied within
            the OperatorRecorder context, includes operations and observables
        operations (List[~.Operations]): list of operations applied within
            the OperatorRecorder context
        observables (List[~.Observables]): list of observables applied within
            the OperatorRecorder context
    """

    def __init__(self):
        self.rec = None

        self.queue = None
        self.operations = None
        self.observables = None

        self.old_context = None

    def __enter__(self):
        self.rec = Recorder(qml.QNode._current_context)

        # store the old context to be returned later
        self.old_context = qml.QNode._current_context

        # set the recorder as the QNode context
        qml.QNode._current_context = self.rec

        self.queue = None
        self.operations = None
        self.observables = None

        return self

    def __exit__(self, *args, **kwargs):
        # Remove duplicates that might have arisen from measurements
        self.queue = list(OrderedDict.fromkeys(self.rec._ops))
        self.operations = list(
            filter(
                lambda op: not (
                    isinstance(op, qml.operation.Observable) and not op.return_type is None
                ),
                self.queue,
            )
        )
        self.observables = list(
            filter(
                lambda op: isinstance(op, qml.operation.Observable) and not op.return_type is None,
                self.queue,
            )
        )

        qml.QNode._current_context = self.old_context

    def __str__(self):
        output = ""
        output += "Operations\n"
        output += "==========\n"
        for op in self.operations:
            if op.parameters:
                params = ", ".join([str(p) for p in op.parameters])
                output += "{}({}, wires={})\n".format(op.name, params, op.wires)
            else:
                output += "{}(wires={})\n".format(op.name, op.wires)

        return_map = {
            qml.operation.Expectation: "expval",
            qml.operation.Variance: "var",
            qml.operation.Sample: "sample",
        }
        output += "\n"
        output += "Observables\n"
        output += "==========\n"
        for op in self.observables:
            if op.parameters:
                params = ", ".join([str(p) for p in op.parameters])
                output += "{}({}({}, wires={}))\n".format(
                    return_map[op.return_type], op.name, params, op.wires
                )
            else:
                output += "{}({}(wires={}))\n".format(return_map[op.return_type], op.name, op.wires)

        return output
