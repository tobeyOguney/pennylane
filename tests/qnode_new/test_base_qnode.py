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
Unit tests for the :mod:`pennylane` :class:`QNode` class.
"""
import contextlib
import io
import textwrap

import pytest
import numpy as np

import pennylane as qml
from pennylane._device import Device
from pennylane.qnode_new.qnode import QNode, QuantumFunctionError, QNode_old


@pytest.fixture(scope="function")
def mock_qnode(mock_device):
    """Provides a circuit for the subsequent tests of the operation queue"""

    def circuit(x):
        qml.RX(x, wires=[0])
        qml.CNOT(wires=[0, 1])
        qml.RY(0.4, wires=[0])
        qml.RZ(-0.2, wires=[1])
        return qml.expval(qml.PauliX(0)), qml.expval(qml.PauliZ(1))

    node = QNode(circuit, mock_device)
    node._construct([1.0], {})
    return node


@pytest.fixture(scope="function")
def operable_mock_device_2_wires(monkeypatch):
    """A mock instance of the abstract Device class that can support qfuncs."""

    dev = Device
    with monkeypatch.context() as m:
        m.setattr(dev, "__abstractmethods__", frozenset())
        m.setattr(dev, 'capabilities', lambda cls: {"model": "qubit"})
        m.setattr(dev, "operations", ["RX", "RY", "CNOT"])
        m.setattr(dev, "observables", ["PauliX", "PauliY", "PauliZ"])
        m.setattr(dev, "reset", lambda self: None)
        m.setattr(dev, "apply", lambda self, x, y, z: None)
        m.setattr(dev, "expval", lambda self, x, y, z: 1)
        yield Device(wires=2)


class TestQNodeOperationQueue:
    """Tests that the QNode operation queue is properly filled and interacted with"""

    def test_operation_ordering(self, mock_qnode):
        """Tests that the ordering of the operations is correct"""

        qnode = mock_qnode
        assert qnode.ops[0].name == "RX"
        assert qnode.ops[1].name == "CNOT"
        assert qnode.ops[2].name == "RY"
        assert qnode.ops[3].name == "RZ"
        assert qnode.ops[4].name == "PauliX"
        assert qnode.ops[5].name == "PauliZ"

    def test_op_descendants_operations_only(self, mock_qnode):
        """Tests that _op_descendants properly extracts the successors that are operations"""

        qnode = mock_qnode
        operation_successors = qnode._op_descendants(qnode.ops[0], only="G")
        assert qnode.ops[0] not in operation_successors
        assert qnode.ops[1] in operation_successors
        assert qnode.ops[4] not in operation_successors

    def test_op_descendants_observables_only(self, mock_qnode):
        """Tests that _op_descendants properly extracts the successors that are observables"""

        qnode = mock_qnode
        observable_successors = qnode._op_descendants(qnode.ops[0], only="E")
        assert qnode.ops[0] not in observable_successors
        assert qnode.ops[1] not in observable_successors
        assert qnode.ops[4] in observable_successors

    def test_op_descendants_both_operations_and_observables(self, mock_qnode):
        """Tests that _op_descendants properly extracts all successors"""

        qnode = mock_qnode
        successors = qnode._op_descendants(qnode.ops[0], only=None)
        assert qnode.ops[0] not in successors
        assert qnode.ops[1] in successors
        assert qnode.ops[4] in successors

    def test_op_descendants_both_operations_and_observables_nodes(self, mock_qnode):
        """Tests that _op_descendants properly extracts all successor nodes"""

        qnode = mock_qnode
        successors = qnode._op_descendants(qnode.ops[0], only=None)
        assert qnode.circuit.operations[0] not in successors
        assert qnode.circuit.operations[1] in successors
        assert qnode.circuit.operations[2] in successors
        assert qnode.circuit.operations[3] in successors
        assert qnode.circuit.observables[0] in successors

    def test_op_descendants_both_operations_and_observables_strict_ordering(self, mock_qnode):
        """Tests that _op_descendants properly extracts all successors"""

        qnode = mock_qnode
        successors = qnode._op_descendants(qnode.ops[2], only=None)
        assert qnode.circuit.operations[0] not in successors
        assert qnode.circuit.operations[1] not in successors
        assert qnode.circuit.operations[2] not in successors
        assert qnode.circuit.operations[3] not in successors
        assert qnode.circuit.observables[0] in successors

    def test_op_descendants_extracts_all_successors(self, mock_qnode):
        """Tests that _op_descendants properly extracts all successors"""

        qnode = mock_qnode
        successors = qnode._op_descendants(qnode.ops[2], only=None)
        assert qnode.ops[4] in successors
        assert qnode.ops[5] not in successors

    def test_print_applied(self, mock_device):
        """Test that printing applied gates works correctly"""

        H = np.array([[0, 1], [1, 0]])

        def circuit(x):
            qml.RX(x, wires=[0])
            qml.CNOT(wires=[0, 1])
            qml.RY(0.4, wires=[0])
            qml.RZ(-0.2, wires=[1])
            return qml.expval(qml.PauliX(0)), qml.var(qml.Hermitian(H, wires=1))

        expected_qnode_print = textwrap.dedent(
            """\
            Operations
            ==========
            RX({x}, wires=[0])
            CNOT(wires=[0, 1])
            RY(0.4, wires=[0])
            RZ(-0.2, wires=[1])

            Observables
            ===========
            expval(PauliX(wires=[0]))
            var(Hermitian([[0 1]
             [1 0]], wires=[1]))"""
        )

        node = QNode(circuit, mock_device)

        # test before construction
        f = io.StringIO()

        with contextlib.redirect_stdout(f):
            node.print_applied()
            out = f.getvalue().strip()

        assert out == "QNode has not yet been executed."

        # construct QNode
        f = io.StringIO()
        node._set_variables([0.1], {})
        node._construct([0.1], {})

        with contextlib.redirect_stdout(f):
            node.print_applied()
            out = f.getvalue().strip()

        assert out == expected_qnode_print.format(x=0.1)


class TestQNodeExceptions:
    """Tests that QNode raises proper errors"""

    def test_current_context_modified_outside_construct(
        self, operable_mock_device_2_wires, monkeypatch
    ):
        """Error: _current_context was modified outside of construct."""

        def circuit(x):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(wires=0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with monkeypatch.context() as m:
            m.setattr(QNode_old, "_current_context", node)
            with pytest.raises(
                QuantumFunctionError,
                match="QNode._current_context must not be modified outside this method.",
            ):
                node(0.5)

    def test_operations_after_observables(self, operable_mock_device_2_wires):
        """Error: qfunc contains operations after observables."""

        def circuit(x):
            qml.RX(x, wires=[0])
            ex = qml.expval(qml.PauliZ(wires=1))
            qml.RY(0.5, wires=[0])
            return qml.expval(qml.PauliZ(wires=0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="gates must precede measured"):
            node(0.5)

    def test_return_of_non_observable(self, operable_mock_device_2_wires):
        """Error: qfunc returns something besides observables."""

        def circuit(x):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(wires=0)), 0.3

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="A quantum function must return either"):
            node(0.5)

    def test_observable_with_no_measurement_type(self, operable_mock_device_2_wires):
        """Error: observable lacks the measurement type."""

        def circuit(x):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(wires=0)), qml.PauliZ(wires=1)

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(
            QuantumFunctionError, match="does not have the measurement type specified"
        ):
            node(0.5)

    def test_observable_not_returned(self, operable_mock_device_2_wires):
        """Error: qfunc does not return all observables."""

        def circuit(x):
            qml.RX(x, wires=[0])
            ex = qml.expval(qml.PauliZ(wires=1))
            return qml.expval(qml.PauliZ(wires=0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="All measured observables must be returned"):
            node(0.5)

    def test_observable_order_violated(self, operable_mock_device_2_wires):
        """Error: qfunc does not return all observables in the correct order."""

        def circuit(x):
            qml.RX(x, wires=[0])
            ex = qml.expval(qml.PauliZ(wires=1))
            return qml.expval(qml.PauliZ(wires=0)), ex

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="All measured observables must be returned"):
            node(0.5)

    def test_mixing_of_cv_and_qubit_operations(self, operable_mock_device_2_wires):
        """Error: qubit and CV operations are mixed in the same qfunc."""

        def circuit(x):
            qml.RX(x, wires=[0])
            qml.Displacement(0.5, 0, wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(
            QuantumFunctionError, match="Continuous and discrete operations are not allowed"
        ):
            node(0.5)

    def test_cv_operations_on_qubit_device(self, operable_mock_device_2_wires):
        """Error: cannot use CV operations on a qubit device."""

        def circuit(x):
            qml.Displacement(0.5, 0, wires=[0])
            return qml.expval(qml.X(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(
            QuantumFunctionError, match="a qubit device; CV operations are not allowed"
        ):
            node(0.5)

    def test_qubit_operations_on_CV_device(self, operable_mock_device_2_wires, monkeypatch):
        """Error: cannot use qubit operations on a CV device."""
        monkeypatch.setattr(operable_mock_device_2_wires, "capabilities", lambda: {"model": "cv"})

        def circuit(x):
            qml.RX(0.5, wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(
            QuantumFunctionError, match="a CV device; qubit operations are not allowed"
        ):
            node(0.5)

    def test_multiple_measurements_on_same_wire(self, operable_mock_device_2_wires):
        """Error: the same wire is measured multiple times."""

        def circuit(x):
            qml.RX(x, wires=[0])
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1)), qml.expval(qml.PauliX(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="can only be measured once"):
            node(0.5)

    def test_invisible_operations(self, operable_mock_device_2_wires):
        """Error: an operation does not affect the measurements."""

        def circuit(x):
            qml.RX(x, wires=[0])
            qml.RX(x, wires=[1])  # on its own component in the circuit graph
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires, properties={"vis_check": True})
        with pytest.raises(QuantumFunctionError, match="cannot affect the output"):
            node(0.5)

    def test_operation_requiring_all_wires(self, operable_mock_device_2_wires):
        """Error: an operation that must be applied to all wires is not
        applied to all wires."""
        class DummyOp(qml.operation.Operation):
            """Dummy operation"""
            num_wires = qml.operation.Wires.All
            num_params = 0
            par_domain = None

        def circuit():
            DummyOp(wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="must act on all wires"):
            node()

    def test_operation_on_nonexistant_wire(self, operable_mock_device_2_wires):
        """Error: an operation is applied to a non-existant wire."""

        def circuit(x):
            qml.RX(x, wires=[0])
            qml.CNOT(wires=[0, 2])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="applied to invalid wire"):
            node(0.5)

    def test_observable_on_nonexistant_wire(self, operable_mock_device_2_wires):
        """Error: an observable is measured on a non-existant wire."""

        def circuit(x):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(2))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(QuantumFunctionError, match="applied to invalid wire"):
            node(0.5)

    def test_bad_wire_argument(self, operable_mock_device_2_wires):
        """Error: wire arguments must be intergers."""

        def circuit(x):
            qml.RX(x, wires=[0.5])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(2))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(TypeError, match="Wires must be integers"):
            node(1)

    def test_arg_as_wire_argument(self, operable_mock_device_2_wires):
        """Error: trying to use a differentiable parameter as a wire argument."""

        def circuit(x):
            qml.RX(0.5, wires=[x])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(2))

        node = QNode(circuit, operable_mock_device_2_wires)
        with pytest.raises(TypeError, match="Wires must be integers"):
            node(1)

    def test_kwarg_as_wire_argument(self, operable_mock_device_2_wires):
        """Error: trying to use a keyword-only parameter as a wire argument in an immutable circuit."""

        def circuit(*, x=None):
            qml.RX(0.5, wires=[x])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, operable_mock_device_2_wires, mutable=False)
        with pytest.raises(TypeError, match="Wires must be integers"):
            node(x=1)

    @pytest.mark.xfail(
        reason="Tests the auxiliary-equals-keyword-only syntax", raises=TypeError, strict=True
    )
    def test_simple_valid_call(self, operable_mock_device_2_wires):
        """Old QNode gives an error here, "got multiple values for argument 'x'"
        """

        def circuit(x=0):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)
        node(0.3)
        assert node.ops[0].parameters[0] == 0.3

    @pytest.mark.xfail(
        reason="Tests the auxiliary-equals-keyword-only syntax", raises=AssertionError, strict=True
    )
    def test_calling_no_kwargs(self, operable_mock_device_2_wires):
        """Various quantum func calling syntax errors."""

        def circuit(x, y=0.2, *args, m=0.3, n):
            circuit.in_args = (x, y, m, n)
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires, mutable=True)

        with pytest.raises(QuantumFunctionError, match="parameter 'x' given twice"):
            node(0.1, x=1.1)
        with pytest.raises(QuantumFunctionError, match="Unknown quantum function parameter 'foo'"):
            node(foo=1)
        with pytest.raises(
            QuantumFunctionError, match="'args' cannot be given using the keyword syntax"
        ):
            node(args=1)
        with pytest.raises(QuantumFunctionError, match="positional parameter 'x' missing"):
            node(n=0.4)
        with pytest.raises(QuantumFunctionError, match="keyword-only parameter 'n' missing"):
            node(0.1)

        # valid calls
        node(x=0.1, n=0.4)
        assert circuit.in_args[2:] == (0.3, 0.4)  # first two are Variables
        node(0.1, n=0.4)
        assert circuit.in_args[2:] == (0.3, 0.4)

    @pytest.mark.xfail(
        reason="Tests the auxiliary-equals-keyword-only syntax", raises=AssertionError, strict=True
    )
    def test_calling_with_kwargs(self, operable_mock_device_2_wires):
        """Various quantum func calling syntax errors."""

        def circuit(x, y=0.2, *, m=0.3, n, **kwargs):
            circuit.in_args = (x, y, m, n)
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires, mutable=True)

        with pytest.raises(QuantumFunctionError, match="parameter 'x' given twice"):
            node(0.1, x=1.1)
        with pytest.raises(
            QuantumFunctionError, match="'kwargs' cannot be given using the keyword syntax"
        ):
            node(kwargs=1)
        with pytest.raises(QuantumFunctionError, match="takes 2 positional parameters, 3 given"):
            node(0.1, 0.2, 100, n=0.4)
        with pytest.raises(QuantumFunctionError, match="positional parameter 'x' missing"):
            node(n=0.4)
        with pytest.raises(QuantumFunctionError, match="keyword-only parameter 'n' missing"):
            node(0.1)

        # valid calls
        node(x=0.1, n=0.4)
        assert circuit.in_args[2:] == (0.3, 0.4)  # first two are Variables
        node(0.1, n=0.4)
        assert circuit.in_args[2:] == (0.3, 0.4)

    def test_calling_bad_errors(self, operable_mock_device_2_wires):
        """Confusing quantum func calling errors and bugs (auxiliary-equals-parameters-with-default syntax)."""

        def circuit(x=0.1):
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires)

        with pytest.raises(TypeError, match="got multiple values for argument 'x'"):
            node(0.3)  # default arg given positionally, wrong error message

    def test_calling_errors(self, operable_mock_device_2_wires):
        """Good quantum func calling syntax errors (auxiliary-equals-parameters-with-default syntax)."""

        def circuit(x, y=0.2, *args, z=0.3):
            circuit.in_args = (x, y, z)
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, operable_mock_device_2_wires, mutable=True)

        with pytest.raises(
            QuantumFunctionError, match="'x' cannot be given using the keyword syntax"
        ):
            node(0.1, x=1.1)
        with pytest.raises(QuantumFunctionError, match="Unknown quantum function parameter 'foo'"):
            node(foo=1)
        with pytest.raises(
            QuantumFunctionError, match="'args' cannot be given using the keyword syntax"
        ):
            node(args=1)
        with pytest.raises(TypeError, match="missing 1 required positional argument: 'x'"):
            node(z=0.4)

        # valid calls
        node(0.1)
        assert circuit.in_args[1:] == (0.2, 0.3)  # first is a Variable
        node(0.1, y=1.2)
        assert circuit.in_args[1:] == (1.2, 0.3)
        node(0.1, z=1.3, y=1.2)
        assert circuit.in_args[1:] == (1.2, 1.3)


class TestQNodeArgs:
    """Tests the handling of calling arguments in the QNode"""

    @pytest.mark.parametrize(
        "x,y",
        zip(np.linspace(-2 * np.pi, 2 * np.pi, 7), np.linspace(-2 * np.pi, 2 * np.pi, 7) ** 2 / 11),
    )
    def test_fanout(self, qubit_device_1_wire, tol, x, y):
        """Tests that qnodes can compute the correct function when the
           same parameter is used in multiple gates."""

        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RZ(y, wires=[0])
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0))

        def analytic_expval(x, y):
            return np.cos(x) ** 2 - np.cos(y) * np.sin(x) ** 2

        node = QNode(circuit, qubit_device_1_wire)
        res = node(x, y)
        assert res == pytest.approx(analytic_expval(x, y), abs=tol)

    def test_multiple_expectation_different_wires(self, qubit_device_2_wires, tol):
        """Tests that qnodes return multiple expectation values."""

        a, b, c = 0.5, 0.54, 0.3

        def circuit(x, y, z):
            qml.RX(x, wires=[0])
            qml.RZ(y, wires=[0])
            qml.CNOT(wires=[0, 1])
            qml.RY(y, wires=[0])
            qml.RX(z, wires=[0])
            return qml.expval(qml.PauliY(0)), qml.expval(qml.PauliZ(1))

        def analytic_expval(a, b, c):
            return [-1 * np.cos(a) * np.cos(b) * np.sin(c), np.cos(a)]

        node = QNode(circuit, qubit_device_2_wires)
        res = node(a, b, c)
        assert res == pytest.approx(analytic_expval(a, b, c), abs=tol)

    def test_multiple_keywordargs_used(self, qubit_device_2_wires, tol):
        """Tests that qnodes can use multiple keyword-only arguments."""

        def circuit(w, *, x=None, y=None):
            qml.RX(x, wires=[0])
            qml.RX(y, wires=[1])
            qml.RZ(w, wires=[0])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, qubit_device_2_wires)
        c = node(1.0, x=np.pi, y=np.pi / 2)
        assert c == pytest.approx([-1.0, 0.0], abs=tol)

    def test_arraylike_args_used(self, qubit_device_2_wires, tol):
        """Tests that qnodes use array-like positional arguments."""

        def circuit(x):
            qml.RX(x[0], wires=[0])
            qml.RX(x[1], wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, qubit_device_2_wires)
        c = node([np.pi, np.pi])
        assert c == pytest.approx([-1.0, -1.0], abs=tol)

    def test_arraylike_keywordargs_used(self, qubit_device_2_wires, tol):
        """Tests that qnodes use array-like keyword-only arguments."""

        def circuit(w, *, x=None):
            qml.RX(x[0], wires=[0])
            qml.RX(x[1], wires=[1])
            qml.RZ(w, wires=[0])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, qubit_device_2_wires)
        c = node(1.0, x=[np.pi, np.pi / 2])
        assert c == pytest.approx([-1.0, 0.0], abs=tol)

    def test_keywordargs_for_wires(self, qubit_device_2_wires, tol):
        """Tests that wires can be passed as keyword-only arguments in mutable circuits."""

        default_q = 0

        def circuit(x, *, q=default_q):
            qml.RX(x, wires=[q])
            return qml.expval(qml.PauliZ(q))

        node = QNode(circuit, qubit_device_2_wires)
        c = node(np.pi, q=1)
        assert node.ops[0].wires == [1]
        assert c == pytest.approx(-1.0, abs=tol)

        c = node(np.pi)
        assert node.ops[0].wires == [default_q]
        assert c == pytest.approx(-1.0, abs=tol)

    def test_keywordargs_used(self, qubit_device_1_wire, tol):
        """Tests that qnodes use keyword arguments."""

        def circuit(w, x=None):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, qubit_device_1_wire)
        c = node(1.0, x=np.pi)
        assert c == pytest.approx(-1.0, abs=tol)

    def test_keywordarg_updated_in_multiple_calls(self, qubit_device_2_wires, tol):
        """Tests that qnodes update keyword arguments in consecutive calls."""

        def circuit(w, x=None):
            qml.RX(w, wires=[0])
            qml.RX(x, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, qubit_device_2_wires)
        c1 = node(0.1, x=0.0)
        c2 = node(0.1, x=np.pi)
        assert c1[1] != c2[1]

    def test_keywordarg_passes_through_classicalnode(self, qubit_device_2_wires, tol):
        """Tests that qnodes' keyword arguments pass through classical nodes."""

        def circuit(w, x=None):
            qml.RX(w, wires=[0])
            qml.RX(x, wires=[1])
            return qml.expval(qml.PauliZ(0)), qml.expval(qml.PauliZ(1))

        node = QNode(circuit, qubit_device_2_wires)

        def classical_node(w, x=None):
            return node(w, x=x)

        c = classical_node(0.0, x=np.pi)
        assert c == pytest.approx([1.0, -1.0], abs=tol)

    def test_keywordargs_with_kwargs(self, qubit_device_1_wire, tol):
        """Tests that nothing happens if unknown keyword arg passed with
        qnodes accepting **kwargs."""
        def circuit(w, x=None, **kwargs):
            qml.RX(x, wires=[0])
            return qml.expval(qml.PauliZ(0))

        node = QNode(circuit, qubit_device_1_wire)
        c = node(1.0, x=np.pi, y=10)
        assert c == pytest.approx(-1.0, abs=tol)


class TestQNodeCaching:
    """Tests for the QNode construction caching"""

    def test_no_caching(self):
        """Test that mutable circuit structure changes on subsequent evalutions."""

        dev = qml.device("default.qubit", wires=2)

        def mutable_circuit(x, *, c=None):
            qml.RX(x, wires=0)
            for i in range(c):
                qml.RX(x, wires=i)
            return qml.expval(qml.PauliZ(0))

        node = QNode(mutable_circuit, dev, mutable=True)

        # first evaluation
        node(0, c=0)
        assert len(node.circuit.operations) == 1
        temp = node.ops[0]

        # second evaluation
        node(0, c=1)
        assert len(node.circuit.operations) == 2
        node.ops[0] is not temp  # all Operations in the circuit are generated anew

    def test_caching(self):
        """Test that non-mutable circuit structure does not change on subsequent evalutions."""

        dev = qml.device("default.qubit", wires=2)

        def non_mutable_circuit(x, *, c=None):
            qml.RX(x, wires=0)
            qml.RX(c, wires=0)
            return qml.expval(qml.PauliZ(0))

        node = QNode(non_mutable_circuit, dev, mutable=False)

        # first evaluation
        node(0, c=0)
        assert len(node.circuit.operations) == 2
        temp = node.ops[0]

        # second evaluation
        node(0, c=1)
        assert len(node.circuit.operations) == 2
        node.ops[0] is temp  # it's the same circuit with the same objects


class TestQNodeInterface:
    """Test for the classical interface"""

    def test_interface_property(self, mock_qnode):
        """Test that the default interface value is 'numpy'"""
        assert mock_qnode.interface == "numpy"


class TestQNodeEvaluate:
    """Test for observable statistic evaluation"""

    @pytest.mark.parametrize(
        "x,y",
        zip(np.linspace(-2 * np.pi, 2 * np.pi, 7), np.linspace(-2 * np.pi, 2 * np.pi, 7) ** 2 / 11),
    )
    def test_evaluate(self, x, y, tol):
        """Tests correct evaluation"""
        dev = qml.device("default.qubit", wires=2)

        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0) @ qml.PauliX(1))

        node = QNode(circuit, dev)
        res = node.evaluate([x, y], {})
        expected = np.sin(y)*np.cos(x)
        assert np.allclose(res, expected, atol=tol, rtol=0)

    @pytest.mark.parametrize(
        "x,y",
        zip(np.linspace(-2 * np.pi, 2 * np.pi, 7), np.linspace(-2 * np.pi, 2 * np.pi, 7) ** 2 / 11),
    )
    def test_obs_evaluate(self, x, y, tol):
        """Tests correct evaluation swapping out the observables"""
        dev = qml.device("default.qubit", wires=2)

        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.expval(qml.PauliZ(0) @ qml.PauliX(1))

        node = QNode(circuit, dev)

        # test standard evaluation
        node = QNode(circuit, dev)
        res = node.evaluate([x, y], {})
        expected = np.sin(y)*np.cos(x)
        assert np.allclose(res, expected, atol=tol, rtol=0)

        # hot-swap the observable
        res = node.evaluate_obs([qml.PauliZ(0) @ qml.PauliZ(1)], [x, y], {})
        expected = np.cos(y)
        assert np.allclose(res, expected, atol=tol, rtol=0)

    def test_single_mode_sample(self):
        """Test that there is only one array of values returned
        for single mode samples"""
        shots = 10
        dev = qml.device("default.qubit", wires=2, shots=shots)

        def circuit(x, y):
            qml.RX(x, wires=[0])
            qml.RY(y, wires=[1])
            qml.CNOT(wires=[0, 1])
            return qml.sample(qml.PauliZ(0) @ qml.PauliX(1))

        node = QNode(circuit, dev)
        res = node(0.432, 0.12)
        assert res.shape == (10,)